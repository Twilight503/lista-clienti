const fs = require('fs');
const path = require('path');
const vm = require('vm');


class FakeClassList {
  add() {}
  remove() {}
  toggle() {}
  contains() { return false; }
}


class FakeElement {
  constructor(id) {
    this.id = id;
    this.value = '';
    this.innerHTML = '';
    this.textContent = '';
    this.disabled = false;
    this.options = [];
    this.className = '';
    this.classList = new FakeClassList();
  }
  addEventListener() {}
  remove() {}
  insertAdjacentElement() {}
  closest() { return null; }
}


async function main() {
  const templatePath = path.join(__dirname, '..', 'templates', 'index.html');
  let script = fs.readFileSync(templatePath, 'utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
  script = script
    .replace('{{ initial_db|tojson }}', 'globalThis.__FIXTURE__')
    .replace('{{ rev|tojson }}', '5')
    .replace('{{ max_transfer_batches|tojson }}', '100');

  const iso = '2026-09-04T10:00:00.000Z';
  const employee = (id, name) => ({ id, name, deleted: false });
  const assignment = (id, agentId, status, extra = {}) => ({
    id,
    agentId,
    status,
    inSheet: status === 'active',
    createdAt: iso,
    lastVerifiedAt: iso,
    noAnswerCount: '2',
    feedback: '',
    history: [],
    ...extra,
  });

  const fixture = {
    version: 12,
    createdAt: { $date: iso },
    employees: [employee('e1', 'Ana'), employee('e2', 'Dan'), employee('e3', 'Mara')],
    deletedEmployeeNames: {},
    clients: [
      { id: 'c_brown', phone: '0711111111', note: 'brown', createdAt: iso, history: [], assignments: [assignment('a1', 'e1', 'brown')] },
      { id: 'c_red', phone: '0722222222', note: 'red', createdAt: iso, history: [], assignments: [assignment('a2', 'e1', 'red')] },
      { id: 'c_red_missing', phone: '0733333333', note: 'red missing', createdAt: iso, history: [], assignments: [assignment('a3', 'e1', 'red'), assignment('a4', 'e2', 'missing')] },
      { id: 'c_conflict', phone: '0744444444', note: 'conflict', createdAt: iso, history: [], assignments: [assignment('a5', 'e1', 'active'), assignment('a6', 'e2', 'red')] },
      { id: 'c_mixed', phone: '0755555555', note: 'mixed', createdAt: iso, history: [], assignments: [assignment('a7', 'e1', 'brown'), assignment('a8', 'e2', 'red')] },
      {
        id: 'c_exhausted',
        phone: '0766666666',
        note: 'exhausted',
        createdAt: iso,
        history: [],
        assignments: [
          assignment('a9', 'e1', 'brown'),
          assignment('a10', 'e2', 'brown', { transferredAt: iso }),
          assignment('a11', 'e3', 'brown', { transferredAt: iso }),
        ],
      },
      { id: 'dup1', phone: '0777777777', note: '', createdAt: iso, history: [], assignments: [assignment('dup_as1', 'e1', 'active')] },
      { id: 'dup2', phone: '0777777777', note: 'merged', createdAt: iso, history: [], assignments: [assignment('dup_as2', 'e1', 'red', { lastVerifiedAt: '2026-09-04T11:00:00Z' })] },
    ],
    deletedRecords: [],
    transfers: [],
    backups: [],
    archivedClients: [],
  };

  const elements = new Map();
  const getElement = id => {
    if (!elements.has(id)) elements.set(id, new FakeElement(id));
    return elements.get(id);
  };
  const document = {
    getElementById: getElement,
    querySelectorAll: () => [],
    addEventListener() {},
    createElement: id => new FakeElement(id),
    execCommand: () => true,
    body: {
      contains: () => false,
      appendChild() {},
      classList: new FakeClassList(),
    },
  };

  let rev = 5;
  const posts = [];
  const context = {
    AbortController,
    Blob: function Blob() {},
    Date,
    DOMParser: function DOMParser() {},
    FileReader: function FileReader() {},
    JSON,
    Map,
    Math,
    Set,
    URL: { createObjectURL: () => '', revokeObjectURL() {} },
    __FIXTURE__: fixture,
    addEventListener() {},
    alert() {},
    clearTimeout,
    confirm: () => true,
    console,
    document,
    fetch: async (_url, options) => {
      posts.push(JSON.parse(options.body));
      rev += 1;
      return { status: 200, ok: true, json: async () => ({ ok: true, rev }), text: async () => '' };
    },
    location: { reload() {}, set href(_value) {} },
    navigator: {},
    posts,
    prompt: () => null,
    setTimeout,
  };
  context.window = context;
  context.globalThis = context;

  script += `
    (async () => {
      const assert = (condition, message) => { if (!condition) throw new Error(message); };
      assert(db.clients.length === 7, 'Clienții cu același telefon nu au fost uniți.');
      const duplicate = db.clients.find(c => c.phone === '0777777777');
      assert(duplicate.note === 'merged', 'Nota clientului duplicat nu a fost păstrată.');
      assert(assignmentOf(duplicate, 'e1').status === 'red', 'Apariția cea mai nouă nu a fost păstrată.');
      assert(assignmentOf(duplicate, 'e1').noAnswerCount === 2, 'Contorul numeric nu a fost normalizat.');
      assert(typeof db.createdAt === 'string', 'Data Mongo nu a fost normalizată.');

      assert(bulkArchiveCandidates('brown').length === 2, 'Număr greșit de candidați MARO.');
      assert(bulkArchiveCandidates('red').length === 3, 'Număr greșit de candidați ROȘU.');
      assert(bulkArchiveProtectedCount('brown') === 1, 'Protecția MARO nu este corectă.');
      assert(bulkArchiveProtectedCount('red') === 2, 'Protecția ROȘU nu este corectă.');
      assert(el('bulkArchiveBrownBtn').textContent.includes('(2)'), 'Contorul butonului MARO nu este randat.');
      assert(el('bulkArchiveRedBtn').textContent.includes('(3)'), 'Contorul butonului ROȘU nu este randat.');
      assert(auditRisk({ expected: Array(10), missing: Array(3) }, Array(7)).risky, 'O listă mică incompletă nu este blocată.');

      el('verifyStatusFilter').value = 'red';
      renderVerification();
      const redFilterHtml = el('verifyRows').innerHTML;
      assert(redFilterHtml.includes("autoSaveFeedback('c_conflict','a6'"), 'Controlul ROȘU al conflictului lipsește.');
      assert(!redFilterHtml.includes("autoSaveFeedback('c_conflict','a5'"), 'Filtrul ROȘU editează greșit apariția ACTIVĂ.');
      el('verifyStatusFilter').value = 'all';
      renderVerification();

      await bulkArchiveStatus('brown');
      await bulkArchiveStatus('red');

      assert(db.archivedClients.length === 5, 'Nu au fost arhivate toate numerele eligibile.');
      assert(db.clients.length === 2, 'Au rămas numere eligibile nearhivate.');
      assert(db.clients.some(c => c.id === 'c_conflict'), 'Un conflict ACTIV + ROȘU a fost arhivat greșit.');
      assert(db.clients.some(c => c.id === 'c_mixed'), 'Un telefon MARO + ROȘU a fost arhivat greșit.');
      assert(posts.length === 2, 'Arhivarea în masă nu a făcut exact două salvări.');
    })()
  `;

  await vm.runInNewContext(script, context, { filename: 'index-inline.js' });
  console.log('Frontend logic smoke: OK');
}


main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
