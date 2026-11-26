// "Bursa" yazılıp hemen ardından "Balıkesir" yazılınca, Bursa'nın yanıtı 450 ms'lik
// bekleme içinde dönerse sonuç listesi açılmamalı. static/app.js'e dokunmadan, yer
// arama bölümünü kaynaktan kesip en küçük sahte DOM ile vm içinde çalıştırır.
// Çalıştırma: node tests/js/search_race.test.js  (bağımlılık yok)
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../../static/app.js"), "utf8");
const start = source.indexOf("/* ---------- Yer arama ---------- */");
const end = source.indexOf("function goTo(");
assert.ok(start > 0 && end > start, "app.js içinde yer arama bölümü bulunamadı");
const section = source.slice(start, end);

function makeEnv() {
  const listeners = {};
  const nodes = {};
  const node = (name) => (nodes[name] ??= {
    name, value: "", hidden: true, children: [],
    addEventListener(type, fn) { (listeners[name + ":" + type] ??= []).push(fn); },
    replaceChildren(...kids) { this.children = kids; },
    closest() { return null; },
  });
  const timers = [];
  const pending = []; // uçuştaki api() çağrıları
  const ctx = {
    console,
    state: { searchSeq: 0 },
    $: (selector) => node(selector),
    el: (tag, cls, text) => ({ tag, cls, text, append() {}, addEventListener() {} }),
    api: (url) => new Promise((resolve, reject) => pending.push({ url, resolve, reject })),
    document: { addEventListener() {} },
    setTimeout: (fn, ms) => { timers.push({ fn, ms }); return timers.length; },
    clearTimeout: (id) => { if (timers[id - 1]) timers[id - 1].fn = null; },
  };
  vm.createContext(ctx);
  vm.runInContext(section, ctx);
  return {
    results: node("#searchResults"),
    type(text) {
      node("#searchInput").value = text;
      (listeners["#searchInput:input"] || []).forEach((fn) => fn({}));
    },
    key(k) { (listeners["#searchInput:keydown"] || []).forEach((fn) => fn({ key: k, preventDefault() {} })); },
    fireTimers() { timers.splice(0).forEach((t) => t.fn && t.fn()); },
    pending,
  };
}
const tick = () => new Promise((r) => setImmediate(r));

(async () => {
  // 1) Asıl senaryo: Bursa uçuşta, kullanıcı Balıkesir yazdı, Bursa yanıtı bekleme içinde döner.
  {
    const env = makeEnv();
    env.type("Bursa");
    env.fireTimers();
    assert.equal(env.pending.length, 1, "Bursa isteği çıkmalı");
    env.type("Balıkesir"); // henüz yeni istek yok: 450 ms bekleme sürüyor
    env.pending[0].resolve([{ name: "Bursa, Türkiye" }]);
    await tick();
    assert.equal(env.results.hidden, true, "Bursa'nın geç yanıtı listeyi açmamalı");
  }
  // 2) Kontrol: Balıkesir'in kendi yanıtı listeyi açar (test yanlış-olumlu değil).
  {
    const env = makeEnv();
    env.type("Bursa");
    env.fireTimers();
    env.type("Balıkesir");
    env.fireTimers();
    assert.equal(env.pending.length, 2);
    env.pending[0].resolve([{ name: "Bursa, Türkiye" }]);
    await tick();
    assert.equal(env.results.hidden, true);
    env.pending[1].resolve([{ name: "Balıkesir, Türkiye" }]);
    await tick();
    assert.equal(env.results.hidden, false, "güncel sorgunun yanıtı listeyi açmalı");
  }
  // 3) Escape ile kapatılan liste, uçuştaki yanıtla geri açılmamalı.
  {
    const env = makeEnv();
    env.type("Bursa");
    env.fireTimers();
    env.key("Escape");
    env.pending[0].resolve([{ name: "Bursa, Türkiye" }]);
    await tick();
    assert.equal(env.results.hidden, true, "Escape sonrası geç yanıt listeyi açmamalı");
  }
  console.log("search_race: 3 senaryo geçti");
})().catch((e) => { console.error(e); process.exit(1); });
