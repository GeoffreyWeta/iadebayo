const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function element(extra = {}) {
  return Object.assign({ checked: false, disabled: false, textContent: '', handlers: {},
    addEventListener(name, callback) { this.handlers[name] = callback; } }, extra);
}
function run(file, globals) {
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../static/js', file), 'utf8'), globals);
}

test('all matching selection enables actions without page checkboxes and can be cleared', () => {
  const note = element(), matching = element({ dataset: { count: '248' } }), all = element();
  const boxes = [element(), element()], actions = [element(), element()];
  const bar = { classList: { toggle() {} },
    querySelector: selector => selector === '[data-bulk-count]' ? note : matching,
    querySelectorAll: () => actions };
  run('staff-admin.js', {
    window: {}, document: {
      querySelector: selector => ({ '[data-bulk-bar]': bar, '[data-check-all]': all })[selector] || null,
      querySelectorAll: selector => selector === 'input[name=pks]' ? boxes : [],
      getElementById: () => null
    }
  });
  assert.ok(actions.every(button => button.disabled));
  matching.checked = true;
  matching.handlers.change();
  assert.ok(actions.every(button => !button.disabled));
  assert.match(note.textContent, /248/);
  assert.ok(boxes.every(box => box.disabled));
  matching.checked = false;
  matching.handlers.change();
  assert.ok(actions.every(button => button.disabled));
  assert.ok(boxes.every(box => !box.disabled));
});

function mailPage(deliver) {
  const send = element(), stop = element(), progress = element(), again = element(), count = element();
  const fresh = [element({ value: '1' }), element({ value: '2' })];
  const repeats = [element({ value: '3' })];
  const nodes = { '[data-mail-send]': send, '[data-mail-stop]': stop,
    '[data-mail-progress]': progress, '[name=again]': again, '[data-recipient-count]': count };
  const form = element({ action: '/staff/c/unfinished/email/',
    querySelector: selector => nodes[selector],
    querySelectorAll: selector => selector === '[data-mail-recipient]' ? fresh :
      selector === '[data-mail-recipient], [data-mail-repeat]' ? fresh.concat(repeats) : [again]
  });
  class Data extends Map {
    constructor() { super([['csrfmiddlewaretoken', 'test'], ['subject', 'Hello'], ['body', 'Continue']]); }
  }
  const requests = [];
  run('staff-mail.js', {
    document: { querySelector: () => form }, FormData: Data,
    window: { fetch: true, FormData: Data, confirm: () => true, addEventListener() {} },
    fetch: async (url, options) => {
      const values = Object.fromEntries(options.body);
      requests.push(values);
      const result = await deliver(values, { send, stop, progress, again });
      return { ok: true, headers: { get: () => 'application/json' }, json: async () => result };
    }
  });
  return { send, stop, progress, again, count, requests,
    submit: () => form.handlers.submit({ preventDefault() {} }) };
}

test('mail progress sends separate recipients and retries only failed requests', async () => {
  let failedOnce = false;
  const page = mailPage(async values => {
    if (values.pks === '2' && !failedOnce) {
      failedOnce = true;
      return { sent: 0, failed: 1, skipped: 0 };
    }
    return { sent: 1, failed: 0, skipped: 0 };
  });
  page.again.checked = true;
  page.again.handlers.change();
  assert.equal(page.count.textContent, 3);
  await page.submit();
  assert.deepEqual(page.requests.map(request => request.pks), ['1', '2', '3']);
  assert.ok(page.requests.every(request => request.bulk_async === '1'));
  assert.match(page.progress.textContent, /2 accepted.*1 failed/);
  await page.submit();
  assert.deepEqual(page.requests.map(request => request.pks), ['1', '2', '3', '2']);
  assert.equal(page.send.disabled, true);
});

test('stop finishes the current email and leaves remaining recipients available', async () => {
  const page = mailPage(async (values, controls) => {
    controls.stop.handlers.click();
    return { sent: 1, failed: 0, skipped: 0 };
  });
  await page.submit();
  assert.equal(page.requests.length, 1);
  assert.equal(page.count.textContent, 1);
  assert.match(page.progress.textContent, /Stopped/);
  assert.equal(page.again.disabled, false);
});
