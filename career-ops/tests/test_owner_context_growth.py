import hashlib
import pytest
import hermes_owner_context as owner

def test_large_reference_is_included_without_truncation(tmp_path):
    data = ('Verified fact.\n' * 12000).encode()
    path = tmp_path / 'career_context.md'
    path.write_bytes(data)
    context, evidence = owner.retrieve('', tmp_path, required=('career_context.md',))
    assert data.decode() in context
    assert evidence[0]['source_bytes'] == evidence[0]['included_bytes'] == len(data)
    assert evidence[0]['sha256'] == evidence[0]['included_sha256'] == hashlib.sha256(data).hexdigest()

def test_empty_and_missing_references_still_fail_closed(tmp_path):
    with pytest.raises(RuntimeError, match='unavailable'):
        owner.retrieve('', tmp_path, required=('career_context.md',))
    (tmp_path / 'career_context.md').write_bytes(b'')
    with pytest.raises(RuntimeError, match='invalid'):
        owner.retrieve('', tmp_path, required=('career_context.md',))
