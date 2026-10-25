"""Compatibility CLI: all LinkedIn state mutations use linkedin_state."""
import argparse
import linkedin_state as state


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--drafts',required=True)
    p.add_argument('--approve-message-id',type=int);p.add_argument('--cancel',action='store_true')
    p.add_argument('--cancel-reason',default='owner cancelled');p.add_argument('--dry-run',action='store_true')
    p.add_argument('--refresh-news',action='store_true')
    a=p.parse_args(argv)
    command=['cancel' if a.cancel else 'reconcile','--drafts',a.drafts]
    if a.cancel:command+=['--reason',a.cancel_reason]
    elif a.approve_message_id is not None:command+=['--approve-message-id',str(a.approve_message_id)]
    if a.refresh_news and not a.cancel:command.append('--refresh-news')
    if a.dry_run:command.append('--dry-run')
    return state.main(command)


if __name__=='__main__':raise SystemExit(main())
