from pathlib import Path


def test_mytemplates_refresh_does_not_rebuild_open_project_detail():
    html = (Path(__file__).resolve().parents[1] / "static" / "index.html").read_text(encoding="utf-8")
    assert "document.getElementById('my-detail')?.querySelector('.card')" in html
    assert "if(_myTplRefreshTimer){ clearTimeout(_myTplRefreshTimer); _myTplRefreshTimer=null; }" in html
    assert "$$('[data-tpl-detail]').forEach(b=>b.onclick=(event)=>{\n      event.stopPropagation();" in html
