// Node harness for mustache_mini.js — run: node backend/templates/mustache_mini.test.js
const { render } = require('./mustache_mini.js');
const assert = require('assert');

// variables + escaping (output must contain entities, not raw < &)
const esc = render('{{x}}', { x: '<i>&"' });
assert.ok(esc.includes('lt;') && esc.includes('amp;') && !esc.includes('<'), 'escaping works');
// raw
assert.strictEqual(render('a {{{x}}} b', { x: '<br>' }), 'a <br> b');
// missing -> empty
assert.strictEqual(render('a {{nope}} b', {}), 'a  b');
// dotted
assert.strictEqual(render('{{a.b}}', { a: { b: 'deep' } }), 'deep');
// section truthy / falsy / zero
assert.strictEqual(render('{{#x}}yes{{/x}}', { x: 1 }), 'yes');
assert.strictEqual(render('{{#x}}yes{{/x}}', { x: 0 }), '');
assert.strictEqual(render('{{#x}}yes{{/x}}', { x: '' }), '');
// inverted incl. zero (PST-not-applicable case)
assert.strictEqual(render('{{^x}}NA{{/x}}', { x: 0 }), 'NA');
assert.strictEqual(render('{{^x}}NA{{/x}}', { x: '5.00' }), '');
// array loop + parent access from item
assert.strictEqual(
  render('{{#items}}{{p}}-{{n}};{{/items}}', { p: 'P', items: [{ n: 1 }, { n: 2 }] }),
  'P-1;P-2;');
// empty array renders nothing; inverted fires
assert.strictEqual(render('{{#items}}x{{/items}}', { items: [] }), '');
assert.strictEqual(render('{{^items}}none{{/items}}', { items: [] }), 'none');
// nesting
assert.strictEqual(
  render('{{#a}}{{#b}}{{v}}{{/b}}{{/a}}', { a: { b: { v: 'deep' } } }),
  'deep');
// HTML comments are stripped (the real template documents syntax in comments)
assert.strictEqual(render('x<!-- {{#unclosed}} -->y', {}), 'xy');

// full template smoke: the real invoice template with a fixture
const fs = require('fs');
const tpl = fs.readFileSync(__dirname + '/invoice.html', 'utf8');
const data = {
  brand_primary_color: '#1d4ed8',
  company_name: 'Ireh Construction',
  company_address: '1951 Kaptey Ave, Coquitlam, BC  V3K 5Z7',
  company_phone: '778-994-6602',
  gst_reg_number: 'BC123456789',
  pst_reg_number: '',
  logo_data_uri: 'data:image/svg+xml;base64,SGVsbG8=',
  invoice_number: 'INV-0007',
  issued_date: '2026-10-25',
  due_date: '2026-11-08',
  invoice_type_label: 'Progress billing — 25% of contract value ($52,500.00)',
  project_name: 'Oakridge Build',
  bill_to_name: 'Dave Miller',
  bill_to_address: '1250 Oakridge Crescent<br>Vancouver, BC',
  line_items: [
    { position: 1, description: 'Progress billing — 25%', amount: '$13,125.00' },
    { position: 2, description: 'CO #1', amount: '$1,000.00' },
  ],
  net_amount: '$14,125.00',
  gst_label: 'GST',
  gst_amount: '$706.25',
  pst_label: 'PST',
  pst_amount: 0,
  amount_due: '$14,831.25',
  holdback_amount: '',
  holdback_label: 'Holdback (10% retained)',
  payment_instructions: 'E-transfer to the office.<br>Or cheque.',
};
const html = render(tpl, data);
assert.ok(html.includes('data:image/svg+xml;base64,SGVsbG8='), 'logo data URI rendered');
assert.ok(html.includes('INV-0007'), 'invoice number');
assert.ok(html.includes('$14,831.25'), 'total due');
assert.ok(html.includes('Not applicable'), 'PST zero -> not applicable');
assert.ok(!html.includes('Holdback (10% retained)'), 'holdback omitted when empty');
assert.ok(!html.includes('$undefined'), 'no undefined leaked');
assert.ok(html.includes('GST #: BC123456789'), 'header GST reg line always present');
assert.ok(html.includes('PST #:'), 'header PST reg line reserved (blank when unset)');
const zeroGst = render(tpl, { ...data, gst_amount: '$0.00', pst_amount: 0 });
assert.ok(zeroGst.includes('$0.00'), 'GST row kept even when zero');
assert.ok(zeroGst.includes('Not applicable'), 'PST zero -> Not applicable row');
assert.ok(html.includes('E-transfer to the office.<br>'), 'payment instructions raw');

console.log('mustache_mini: all tests passed; rendered template bytes:', html.length);
