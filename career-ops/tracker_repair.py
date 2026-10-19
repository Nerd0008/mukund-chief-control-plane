"""Conservative, explicit UK hyperlink/duplicate repair using Career Ops verification."""
import copy,datetime as dt,hashlib,json,os,pathlib,shutil,uuid
import openpyxl
import tracker_writer as tw
from tracker_integrity import bind_links
from posting_identity import company_key, identity_keys

def _rows(ws):
    return [[(c.value,tuple(c._style) if c.has_style else None,c.data_type,
              (c.comment.text,c.comment.author) if c.comment else None) for c in row]
            for row in ws.iter_rows()]

def repair(path,profiles,backup_dir,duplicate_rows=(),apply=False,resolved_urls=None):
    path=pathlib.Path(path);cfg=dict(tw.region_config(profiles,'uk'))
    if cfg.get('column_ceiling')!=6:raise ValueError('Unexpected UK layout')
    # Caller-supplied employer destinations for rows whose own URL names no requisition
    # (aggregator/re-seller listings). Supplying one lets the row collapse onto the
    # employer row it duplicates instead of needing a guessed URL match.
    resolved_urls={int(k):v for k,v in (resolved_urls or {}).items()}
    backup_dir=pathlib.Path(backup_dir);backup_dir.mkdir(parents=True,exist_ok=True)
    lock=path.with_suffix(path.suffix+'.career-mail.lock')
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    staged=path.with_name(path.stem+'.repair-'+uuid.uuid4().hex+'.xlsx')
    wb=None
    try:
        before=tw.sha256_file(path);wb=openpyxl.load_workbook(path);ws=wb[cfg['sheet']]
        original=_rows(ws);dimensions={r:copy.copy(d) for r,d in ws.row_dimensions.items()}
        if ws.max_column!=6 or any(c.data_type=='f' for row in ws.iter_rows() for c in row):
            raise ValueError('Unexpected columns/formulas; requires explicit dependency review')
        archived=[]
        for row in sorted(set(duplicate_rows)):
            if row<cfg['first_data_row'] or row>ws.max_row:raise ValueError('Invalid duplicate row')
            values=[ws.cell(row,c).value for c in range(1,7)]
            if values[5]!='Not Applied':raise ValueError('Never remove applied/owner-status records')
            key=tw.normalize_url(values[3])
            company=values[1]
            matches=[r for r in range(cfg['first_data_row'],ws.max_row+1) if r not in duplicate_rows
                     and tw.normalize_url(ws.cell(r,4).value)==key
                     and all(ws.cell(r,c).value==values[c-1] for c in (1,2,3,5,6))]
            basis='identical URL and cells'
            if not matches:
                # Same vacancy, different URL: an employer ATS URL, an aggregator listing
                # and a re-seller link all name one requisition. Identity is the ATS
                # requisition ID scoped to the employer, never company/title alone.
                identities=identity_keys(company,values[3],resolved_urls.get(row))
                if identities:
                    matches=[r for r in range(cfg['first_data_row'],ws.max_row+1)
                             if r not in duplicate_rows
                             and identities & identity_keys(ws.cell(r,2).value,ws.cell(r,4).value)
                             and company_key(ws.cell(r,2).value)==company_key(company)]
                    basis='same ATS requisition'
            if not matches:raise ValueError('No exact compatible retained duplicate')
            archived.append({'original_row':row,'retained_original_rows':matches,
                             'match_basis':basis,'values':values})
        missing=[ws.cell(r,4).coordinate for r in range(cfg['first_data_row'],ws.max_row+1)
                 if str(ws.cell(r,4).value or '').startswith('http') and not ws.cell(r,4).hyperlink]
        for row in sorted(set(duplicate_rows),reverse=True):ws.delete_rows(row)
        for r in list(ws.row_dimensions):del ws.row_dimensions[r]
        for r,d in dimensions.items():
            if r in duplicate_rows:continue
            target=r-sum(deleted<r for deleted in duplicate_rows);d.index=target
            ws.row_dimensions[target]=d
        bind_links(ws,cfg)
        expected=[row for i,row in enumerate(original,1) if i not in duplicate_rows]
        if _rows(ws)!=expected:raise ValueError('Unexpected core cell/style/comment change')
        wb.save(staged);wb.close();wb=None
        check=openpyxl.load_workbook(staged)
        try:
            if _rows(check[cfg['sheet']])!=expected:raise ValueError('Round-trip changed owner data/style')
        finally:check.close()
        verification=tw.verify_workbook(staged,cfg)
        if not verification['ok']:raise ValueError('Staged repair failed: '+repr(verification['problems']))
        result={'applied':False,'sha256_before':before,'missing_links_repaired':missing,
                'duplicate_rows_archived':archived,'verification':verification,
                'core_cells_preserved_except_explicit_duplicate':True}
        if not apply:return result
        backup=backup_dir/(path.stem+'.pre-repair-'+uuid.uuid4().hex+'.xlsx')
        shutil.copy2(path,backup)
        if tw.sha256_file(backup)!=before:raise ValueError('Backup mismatch/concurrent change')
        result['backup']=str(backup)
        (backup_dir/'repair-plan.json').write_text(json.dumps(result,default=str,indent=2),encoding='utf-8')
        if tw.sha256_file(path)!=before:raise ValueError('Concurrent workbook drift; commit aborted')
        staged_hash=tw.sha256_file(staged);os.replace(staged,path)
        post=tw.verify_workbook(path,cfg)
        if not post['ok']:
            if tw.sha256_file(path)==staged_hash:
                restore=path.with_suffix('.restore-tmp.xlsx');shutil.copy2(backup,restore);os.replace(restore,path)
            raise ValueError('Post-write verification failed; safe rollback attempted')
        result.update(applied=True,sha256_after=tw.sha256_file(path),verification=post)
        (backup_dir/'repair-result.json').write_text(json.dumps(result,default=str,indent=2),encoding='utf-8')
        return result
    finally:
        if wb is not None:wb.close()
        staged.unlink(missing_ok=True);os.close(fd);lock.unlink()
