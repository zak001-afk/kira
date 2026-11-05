"""Tests des nouveaux controles : arret immediat, liste noire, modification
de tache, compteur X/Y (sans navigateur, sans toucher aux groupes)."""
from __future__ import annotations

from io import BytesIO

from postpilot import agent, config, store
from postpilot.platforms import facebook as fb


def setup_function():
    config.ensure_dirs()
    store.save_links([])
    store.save_tasks([])
    store.clear_link_errors()
    for b in store.blacklist():
        store.remove_blacklist(b['url'])


def test_cancel_flags():
    assert store.is_cancelled('x') is False
    store.request_cancel('x')
    assert store.is_cancelled('x') is True
    store.clear_cancel('x')
    assert store.is_cancelled('x') is False
    store.request_cancel('')
    assert store.is_cancelled('') is False


def test_aggregate_cancelled():
    res = fb._aggregate([('u1', {'ok': True}), ('u2', {'ok': False})],
                        3, cancelled=True)
    assert res['ok'] is False
    assert '1/3' in res['message']


def test_human_pause_around_10s_and_varies():
    vals = {fb._human_pause() for _ in range(30)}
    assert len(vals) > 1           # varie à chaque fois
    assert all(10 <= v <= 13 for v in vals)   # ~10 s entre deux publications


def test_campaign_budget_covers_long_runs():
    assert fb._campaign_budget(1) == 300.0
    assert fb._campaign_budget(199) > 90.0   # plus de mort à 90 s
    assert fb._campaign_budget(199) == 199 * 180.0


def test_sleep_cancelable_stops_fast():
    import time
    store.request_cancel('t1')
    t0 = time.time()
    assert fb._sleep_cancelable(30, 't1') is False
    assert time.time() - t0 < 5
    store.clear_cancel('t1')
    assert fb._sleep_cancelable(0.1, 't1') is True


def test_blacklist_roundtrip_and_persist():
    assert store.add_blacklist('https://www.facebook.com/groups/1') is True
    assert store.is_blacklisted('https://www.facebook.com/groups/1') is True
    assert store.is_blacklisted('https://www.facebook.com/groups/2') is False
    assert any(i['url'] == 'https://www.facebook.com/groups/1'
               for i in config.load_json(config.BLACKLIST_FILE, []))
    assert store.remove_blacklist('https://www.facebook.com/groups/1') is True
    assert store.is_blacklisted('https://www.facebook.com/groups/1') is False


def test_blacklist_link_error_removes_and_bans_and_unchecks():
    store.save_links([{'id': 'a1', 'platform': 'facebook',
                       'url': 'https://www.facebook.com/groups/9',
                       'selected': True}])
    store.add_link_error('https://www.facebook.com/groups/9', 'boom')
    res = agent.blacklist_link_error('https://www.facebook.com/groups/9')
    assert res['ok'] is True
    assert res['link_errors'] == []
    assert any(b['url'] == 'https://www.facebook.com/groups/9'
               for b in res['blacklist'])
    assert store.links()[0]['selected'] is False
    refused = agent.add_link('https://www.facebook.com/groups/9', 'facebook')
    assert refused['ok'] is False and 'noire' in refused['message']
    assert agent.unblacklist('https://www.facebook.com/groups/9')['ok'] is True
    assert agent.add_link('https://www.facebook.com/groups/9',
                          'facebook')['ok'] is True


def test_blacklist_export_xlsx():
    """Export Excel de la liste noire : en-tête + chaque lien banni."""
    import io as _io
    from openpyxl import load_workbook
    from postpilot import xlsx as xlsx_mod
    store.add_blacklist("https://www.facebook.com/groups/b1")
    store.add_blacklist("https://www.facebook.com/groups/b2")
    data = xlsx_mod.blacklist_export_xlsx(store.blacklist())
    wb = load_workbook(_io.BytesIO(data))
    rows = list(wb.active.iter_rows(values_only=True))
    assert rows[0] == ("Lien", "Banni le")
    urls = [r[0] for r in rows[1:]]
    assert "https://www.facebook.com/groups/b1" in urls
    assert "https://www.facebook.com/groups/b2" in urls


def test_excel_import_skips_blacklisted():
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws['A1'] = 'https://www.facebook.com/groups/ok1'
    ws['A2'] = 'https://www.facebook.com/groups/ban1'
    buf = BytesIO()
    wb.save(buf)
    store.add_blacklist('https://www.facebook.com/groups/ban1')
    res = agent.import_links_file('liens.xlsx', buf.getvalue())
    assert res['ok'] is True
    assert res['added'] == 1
    assert 'liste noire' in res['message']
    urls = [lk['url'] for lk in res['links']]
    assert 'https://www.facebook.com/groups/ok1' in urls
    assert 'https://www.facebook.com/groups/ban1' not in urls


def _make_task():
    return store.add_task({
        'platform': 'facebook', 'kind': 'post', 'target': 'profile',
        'content': 'ancien texte', 'interval_seconds': 3600,
        'summary': 'ancienne',
    })


def test_update_task_fields_ok():
    t = _make_task()
    res = agent.update_task_fields(t['id'], {
        'content': 'nouveau texte', 'interval_minutes': '30',
        'media': '', 'start_at': '', 'end_at': '',
    })
    assert res['ok'] is True, res
    fresh = next(x for x in store.tasks() if x['id'] == t['id'])
    assert fresh['content'] == 'nouveau texte'
    assert fresh['interval_seconds'] == 1800
    assert 'nouveau texte' in fresh['summary']
    store.remove_task(t['id'])


def test_update_task_fields_bad():
    t = _make_task()
    assert agent.update_task_fields('zzz', {'content': 'x'})['ok'] is False
    assert agent.update_task_fields(t['id'], {'content': '  '})['ok'] is False
    bad = agent.update_task_fields(t['id'], {'interval_minutes': '9999'})
    assert bad['ok'] is False
    bad2 = agent.update_task_fields(t['id'], {
        'start_at': '2030-01-02T10:00', 'end_at': '2030-01-01T10:00'})
    assert bad2['ok'] is False
    store.remove_task(t['id'])
