// The phone app's full update on a computer: the real phone parts (convert, plan, drive image, UF2) run on a pad's
// files (a backup folder, as padrepl.py backup makes), with the update package. Writes into OUTDIR:
//   drive.img (the FAT volume, for mtools / fsck), fw.uf2 + drive.uf2 (copy both to RPI-RP2, in that order, e.g.
//   padrepl.py test flash fw.uf2 drive.uf2), plan.json (each file's path, size and SHA-1; the notes).
//   node tools/dev/tests/phone_image.mjs BACKUP_DIR UID_HEX OUTDIR [--label CIRCUITPY] [--flash-mb 16] [--fake-secret]
// --fake-secret: puts a made-up FIRMWARE_04 secret.json (2 layers, encrypted to UID) in, to test the secret pages.
// Prints the notes, never a key's contents.
import fs from 'fs';
import path from 'path';
import vm from 'vm';
import {fileURLToPath} from 'url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const APPDIR = path.join(HERE, '..', '..', '..', 'EMBER_01', 'app');
const FROZEN = path.join(HERE, '..', '..', '..', 'EMBER_01', 'BUILD_FROZEN');
const args = process.argv.slice(2);
const opt = (name, dflt) => { const i = args.indexOf(name); return i < 0 ? dflt : args[i + 1]; };
const [backup, uid, outDir] = args;
if (!outDir) { console.log('usage: phone_image.mjs BACKUP_DIR UID_HEX OUTDIR [--label L] [--flash-mb N] [--fake-secret]'); process.exit(2); }
const label = opt('--label', 'CIRCUITPY'), flashMB = +opt('--flash-mb', 16);
// --as-is PACKAGE.zip: no converting: that package's drive + the backup's files as they are (e.g. to put a test pad
// back on FIRMWARE_04 with its old files, to test the phone's update from the old firmware)
const asIs = opt('--as-is', null);

const ctx = vm.createContext({console, TextEncoder, TextDecoder, crypto: globalThis.crypto, atob, btoa, Blob, Response,
    DecompressionStream, Uint8Array, Uint16Array, DataView, ArrayBuffer, Date, Math, JSON, Promise, Set, Map, Object, Array,
    String, Number, Error, RegExp, parseInt, setTimeout});
for (const part of ['padlists', 'keynames', 'keymap', 'convert/from_v3', 'convert/from_old', 'secret', 'share_format',
                    'phone/fwimage', 'phone/plan']) {
    const html = fs.readFileSync(path.join(APPDIR, 'parts', part + '.html'), 'utf8');
    for (const m of html.matchAll(/<script>([\s\S]*?)<\/script>/g)) vm.runInContext(m[1], ctx, {filename: part});
}
const run = code => vm.runInContext(code, ctx);

// the pad's files, as the phone reads them (PY_WALK: lib / toolkit / app not read)
const files = {}, dirs = [];
(function walk(rel) {
    for (const n of fs.readdirSync(path.join(backup, rel))) {
        const r = rel ? rel + '/' + n : n, full = path.join(backup, r);
        if (fs.statSync(full).isDirectory()) { dirs.push(r); if (!/^(lib|toolkit|app|system volume information|\.fseventsd|lost\.dir)$/i.test(r)) walk(r); }
        else files[r] = new Uint8Array(fs.readFileSync(full));
    }
})('');
ctx.__files = files; ctx.__dirs = dirs; ctx.__uid = uid;
const pkgFile = fs.readdirSync(FROZEN).filter(n => /^MP1_Ember_update_.*\.zip$/.test(n)).sort().pop();
ctx.__pkgBytes = new Uint8Array(fs.readFileSync(asIs || path.join(FROZEN, pkgFile)));
ctx.__asIs = !!asIs;
if (args.includes('--fake-secret')) {
    await run(`(async () => {
        const fake = [{name: 'TESTVAULT', keys: [{icon: 'User', text: 'test-user'}, {icon: 'Pass', text: 'not-a-real-one'}], encoder: {icon: 'Vol'}},
                      {name: 'TEST2', keys: [{icon: 'Hi', text: 'hello'}]}];
        __files['secret.json'] = new TextEncoder().encode(await secretText(fake, secretKeyFromUid(__uid)));
    })()`);
}
const plan = await run(`(async () => {
    const pkg = await readPackage(__pkgBytes, 'test');
    const plan = __asIs ? {notes: ['as is: ' + pkg.info.fw], kind: 'as is', layers: 0, pages: 0, undrawn: 0,
        files: pkg.drive.map(f => ({path: f.path, data: f.data})).concat(Object.entries(__files).filter(([p]) => !pkg.drive.some(f => f.path.toLowerCase() === p.toLowerCase())).map(([path, data]) => ({path, data})))}
        : await planEmber(pkg, __files, __dirs, __uid, new Date(2026, 10, 21, 12, 0));
    const img = fatImage(plan.files, ${flashMB}, ${JSON.stringify(label)}, new Date(2026, 10, 21, 12, 0));
    const uf2 = makeUf2(pkg.uf2, img.runs);
    const list = [];
    for (const f of plan.files) if (!f.dir) list.push({path: f.path, size: f.data.length, sha1: await sha1(f.data)});
    // secret pages written: open them again with the same key (a check, nothing printed from inside)
    let pages = null;
    const sj = plan.files.find(f => f.path === 'secret.json');
    if (sj) { const l = await secretOpen(new TextDecoder().decode(sj.data), secretKeyFromUid(__uid)); pages = l.map(L => L && L.ember === 'layer' ? 'ember layer, ' + (L.keys || []).filter(Boolean).length + ' keys' : 'NOT EMBER'); }
    return {pkg: pkg.info, notes: plan.notes, kind: plan.kind, layers: plan.layers, pages: plan.pages, undrawn: plan.undrawn, list, img, uf2, pagesCheck: pages,
            dirs: plan.files.filter(f => f.dir).map(f => f.path)};
})()`);
fs.mkdirSync(outDir, {recursive: true});
const image = Buffer.alloc(plan.img.sectors * 512);
for (const [sector, bytes] of plan.img.runs) Buffer.from(bytes).copy(image, sector * 512);
fs.writeFileSync(path.join(outDir, 'drive.img'), image);
fs.writeFileSync(path.join(outDir, 'fw.uf2'), plan.uf2.fw);
fs.writeFileSync(path.join(outDir, 'drive.uf2'), plan.uf2.drive);
fs.writeFileSync(path.join(outDir, 'plan.json'), JSON.stringify({notes: plan.notes, files: plan.list, dirs: plan.dirs}, null, 1));
console.log('package', pkgFile, plan.pkg.fw, '| kind', plan.kind, '| layers', plan.layers, '| secret pages', plan.pages, plan.pagesCheck ? '(' + plan.pagesCheck.join('; ') + ')' : '', '| undrawn', plan.undrawn);
console.log('notes:\n  - ' + plan.notes.join('\n  - '));
console.log('drive files:', plan.list.length, '| used', plan.img.used, 'of', plan.img.size, '| fw.uf2', plan.uf2.fw.length, '| drive.uf2', plan.uf2.drive.length);
