import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_adversarial_focus_gate_is_wired_to_the_real_browser_check():
    package = json.loads((ROOT / 'frontend/package.json').read_text(encoding='utf-8'))
    gate = package['scripts']['gate']
    assert 'node --test scripts/check_focus_mode.test.mjs' in gate
    browser_test = (ROOT / 'frontend/scripts/check_focus_mode.test.mjs').read_text(encoding='utf-8')
    for evidence in (
        "test('Focus keeps Context while displaying the visualization in Focus'",
        "page.goto(`${server.url}app?case=C01&view=context`)",
        "page.locator('[data-focus-shell] .softqp-scene-svg').waitFor()",
        "page.locator('[data-focus-group=\"context\"]')",
        "page.getByRole('button', { name: 'Controls', exact: true })",
        "page.locator('[data-focus-exit]').click()",
        "page.goto(`${server.url}app?case=C01&view=context&focus=1`)",
    ):
        assert evidence in browser_test, f'Focus browser test lost required scenario/assertion: {evidence}'
