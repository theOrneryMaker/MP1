// mp1files.js - open and save the macropad's files for the configurator and settings pages.
//
// The files can be plain JSON (keymap.json) or the same JSON wrapped as a small script
// (keymap.js: "var MP1_KEYMAP = {...};"). Pages load the .js file from their own folder
// automatically with a <script> tag; browsers don't let a page read a .json file there.
// Reading takes the text between the first "{" and the last "}", so either form works.
//
// Drive folder (Chrome / Edge): "Connect folder" once, pick the CIRCUITPY drive (or any
// folder). The browser remembers it; after that "Open from drive" / "Save to drive" read
// and write keymap.json or settings.json there directly. Before saving, the old file is
// kept as <name>.bak. The browser may ask once per session to allow editing.
//
// Open… / Save as… work in every browser: a file picker, and a save dialog where the
// browser has one (otherwise the file goes to the Downloads folder).
const MP1Files = (() => {
    const DB = 'mp1-files', STORE = 'handles', KEY = 'drive-folder';
    const hasFolders = typeof window !== 'undefined' && 'showDirectoryPicker' in window;
    let folder = null;

    function store(mode, action) {
        return new Promise((resolve, reject) => {
            const open = indexedDB.open(DB, 1);
            open.onupgradeneeded = () => open.result.createObjectStore(STORE);
            open.onerror = () => reject(open.error);
            open.onsuccess = () => {
                const tx = open.result.transaction(STORE, mode);
                const req = action(tx.objectStore(STORE));
                tx.oncomplete = () => resolve(req ? req.result : undefined);
                tx.onerror = () => reject(tx.error);
            };
        });
    }

    async function remembered() {
        if (folder || !hasFolders) return folder;
        let found = null;
        try {      // never wait more than a moment for the browser's storage
            const timeout = new Promise(resolve => setTimeout(() => resolve(null), 1500));
            found = (await Promise.race([store('readonly', s => s.get(KEY)), timeout])) || null;
        } catch (e) { found = null; }
        if (!folder) folder = found;        // a folder picked meanwhile (Connect) wins
        return folder;
    }

    async function allowed(handle, ask) {
        const opts = {mode: 'readwrite'};
        if ((await handle.queryPermission(opts)) === 'granted') return true;
        return ask && (await handle.requestPermission(opts)) === 'granted';
    }

    // Pick (or re-pick) the drive folder
    async function connect() {
        folder = await window.showDirectoryPicker({id: 'mp1-drive', mode: 'readwrite'});
        try { await store('readwrite', s => s.put(folder, KEY)); } catch (e) { /* remembered for this visit only */ }
        return folder.name;
    }

    async function ready() {
        const h = await remembered();
        if (h && await allowed(h, true)) return h;
        await connect();
        return folder;
    }

    async function folderName() {
        const h = await remembered();
        return h ? h.name : '';
    }

    async function readFrom(name) {
        const dir = await ready();
        let handle;
        try { handle = await dir.getFileHandle(name); }
        catch (e) { throw new Error(`There's no ${name} in "${dir.name}". Is that the CIRCUITPY drive?`); }
        return (await handle.getFile()).text();
    }

    async function writeTo(name, text) {
        const dir = await ready();
        try {                                       // keep the previous version as name.bak
            const old = await (await (await dir.getFileHandle(name)).getFile()).text();
            const bak = await (await dir.getFileHandle(name + '.bak', {create: true})).createWritable();
            await bak.write(old);
            await bak.close();
        } catch (e) {
            if (e.name !== 'NotFoundError') throw e;
        }
        const out = await (await dir.getFileHandle(name, {create: true})).createWritable();
        await out.write(text);
        await out.close();
        return dir.name;
    }

    function download(name, text) {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([text], {type: 'application/json'}));
        a.download = name;
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    }

    // Save dialog where the browser has one; otherwise download. Returns a short description.
    async function saveAs(name, text) {
        if ('showSaveFilePicker' in window) {
            const handle = await window.showSaveFilePicker({
                id: 'mp1-save', suggestedName: name,
                types: [{description: 'JSON file', accept: {'application/json': ['.json']}}],
            });
            const out = await handle.createWritable();
            await out.write(text);
            await out.close();
            return `Saved ${handle.name}`;
        }
        download(name, text);
        return `Downloaded ${name}`;
    }

    // File picker; resolves with the text (and file name), or null if cancelled
    function openFile() {
        return new Promise(resolve => {
            const input = document.createElement('input');
            input.type = 'file';
            input.accept = '.js,.json,application/json,text/javascript';
            input.onchange = () => {
                const file = input.files[0];
                if (!file) return resolve(null);
                file.text().then(text => resolve({name: file.name, text}));
            };
            input.click();
        });
    }

    const cancelled = e => e && (e.name === 'AbortError' || e.name === 'NotAllowedError');

    // ─── .js / .json contents ───
    function parse(text) {
        const start = text.indexOf('{'), end = text.lastIndexOf('}');
        if (start < 0 || end < start) throw new Error('no { ... } found');
        return JSON.parse(text.slice(start, end + 1));
    }
    function wrap(name, jsonText, note) {
        return `// ${note}\nvar ${name} = ${jsonText.trimEnd()};\n`;
    }
    // First of these names that exists in the drive folder: {name, text}
    async function readFirst(names) {
        const dir = await ready();
        for (const name of names) {
            try { return {name, text: await (await (await dir.getFileHandle(name)).getFile()).text()}; }
            catch (e) { if (e.name !== 'NotFoundError') throw e; }
        }
        throw new Error(`There's no ${names.join(' or ')} in "${dir.name}". Is that the CIRCUITPY drive?`);
    }
    // Save dialog offering .js and .json; the name chosen decides which is written.
    // contents = {js, json}. Falls back to a download of suggestedName.
    async function saveAsEither(suggestedName, contents) {
        const asJson = n => /\.json$/i.test(n);
        if ('showSaveFilePicker' in window) {
            const js = {description: 'Script file (.js): the web pages load it automatically', accept: {'text/javascript': ['.js']}};
            const json = {description: 'JSON file (.json)', accept: {'application/json': ['.json']}};
            const handle = await window.showSaveFilePicker({
                id: 'mp1-save', suggestedName, types: asJson(suggestedName) ? [json, js] : [js, json],
            });
            const out = await handle.createWritable();
            await out.write(asJson(handle.name) ? contents.json : contents.js);
            await out.close();
            return `Saved ${handle.name}`;
        }
        download(suggestedName, asJson(suggestedName) ? contents.json : contents.js);
        return `Downloaded ${suggestedName}`;
    }

    return {hasFolders, connect, folderName, readFrom, readFirst, writeTo, saveAs, saveAsEither, openFile,
            download, cancelled, parse, wrap};
})();
