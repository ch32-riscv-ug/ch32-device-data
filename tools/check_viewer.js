// pins.html の中身を、ブラウザ無しで確かめる → 終了コード
//
// **viewer にも検査が要る。** G1（series view の Defaults が先頭型番だけを見て
// いた）は、CH32V006 の series view で SWCLK と UART が全部 `-` になるという
// 目に見える誤りだったのに、誰も気付かないまま残っていた。表には
// `check_tables.py` があり、文書には `check_docs.py` があるが、
// **表示だけが検査の外**だったため。
//
// やり方は、pins.html の `<script>` を DOM 無しで評価して関数を取り出し、
// 正本の CSV を食わせて出力を見る。ブラウザも DOM 実装も要らない
// （CI に node があれば動く）。ここで固定するのは**壊れたら分かる少数の事実**で、
// 見た目ではない。
//
// 実行:
//     node tools/check_viewer.js
"use strict";
const fs = require("fs");
const path = require("path");

const REPO = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(REPO, "pins.html"), "utf8");
const source = html.match(/<script>\n"use strict";([\s\S]*?)<\/script>/)[1]
  .replace(/Promise\.all\(\[[\s\S]*$/, "");   // 起動部分（fetch）は読まない

// 画面の状態。checkbox と入力欄はここで差し替える。
const ui = { chip: "", search: "", splittim: false, features: [], routes: [] };
const element = id => ({
  get value() { return ui[id] ?? ""; }, set value(v) { ui[id] = v; },
  get checked() { return !!ui[id]; }, set checked(v) { ui[id] = v; },
  textContent: "", innerHTML: "",
  append() {}, appendChild() {}, addEventListener() {}, remove() {},
  querySelectorAll: () => [],
});
const document_ = {
  getElementById: element,
  querySelectorAll: sel => (sel.includes("features") ? ui.features : ui.routes)
    .map(value => ({ value, checked: true })),
  createElement: () => element("_"),
};
const api = new Function("document", "location", "history", source + `
  return { defaultsLine, matrixHTML, comparisonHTML, selection, chooserHTML,
           absentInstances, state };`
)(document_, { search: "", pathname: "/pins.html" }, { replaceState() {} });

function csv(file) {
  const text = fs.readFileSync(path.join(REPO, file), "utf8");
  const lines = text.split("\n").filter(l => l.length);
  const head = lines.shift().split(",");
  return lines.map(line => {
    const cells = []; let cell = "", quoted = false;
    for (let i = 0; i < line.length; i++) {
      const c = line[i];
      if (quoted) {
        if (c === '"') { if (line[i + 1] === '"') { cell += '"'; i++; } else quoted = false; }
        else cell += c;
      } else if (c === '"') quoted = true;
      else if (c === ",") { cells.push(cell); cell = ""; }
      else cell += c;
    }
    cells.push(cell);
    return Object.fromEntries(head.map((h, i) => [h, cells[i] ?? ""]));
  });
}

Object.assign(api.state, {
  products: csv("catalog/products.csv"),
  roles: csv("index/pinout.csv"),
  caps: csv("index/capabilities.csv"),
  attrs: csv("evidence/product_attributes.csv"),
  remap: csv("evidence/remap_fields.csv"),
});

const bad = [];
const check = (name, ok, saw) => { if (!ok) bad.push(`${name}: ${saw}`); };
const partsOf = key => api.state.products
  .filter(p => p.series === key || p.part_number === key).map(p => p.part_number);
const columnsOf = h => [...h.matchAll(/<th>([^<]*)<\/th>/g)].map(m => m[1]);

// 1. series view の Defaults は series の全型番を見る（G1）。CH32V006 の先頭品
//    (D8U7) には USART1 が既定で出ていないので、先頭だけを見ると PD5 が消える。
{
  const line = api.defaultsLine(partsOf("CH32V006"));
  check("defaults(CH32V006) が全型番の和になっていない",
        line.includes("PD5") && line.includes("PD6") && line.includes("PB3"),
        line.replace(/<[^>]+>/g, ""));
  check("package 差の印が出ていない", line.includes("*"), line.replace(/<[^>]+>/g, ""));
  // 単一型番の series（差が無い）では印を出さない。
  const v307 = api.defaultsLine(partsOf("CH32V307"));
  check("差の無い series に印が出ている", !v307.includes("*"), v307.replace(/<[^>]+>/g, ""));
}

// 2. 列順（G8）。debug と通信が先、TIM は既定で1列。
{
  ui.chip = "CH32V307VCT6";
  const columns = columnsOf(api.matrixHTML(["CH32V307VCT6"], true).html);
  check("列順が COLUMN_ORDER どおりでない",
        columns.slice(0, 4).join() === "#,SWD,SYS,USART", columns.join(" "));
  check("TIM が既定で1列になっていない",
        columns.filter(c => /^TIM/.test(c)).length === 1, columns.join(" "));
  ui.splittim = true;
  const split = columnsOf(api.matrixHTML(["CH32V307VCT6"], true).html);
  check("split TIM が instance 別にならない",
        split.filter(c => /^TIM\d/.test(c)).length > 5, split.join(" "));
  ui.splittim = false;
}

// 3. 検索は正規化した名前にも当たる（G8）。CH32V003 は資料が `SWIO` と綴る。
{
  ui.chip = "CH32V003F4P6";
  ui.search = "SWDIO";
  const hit = api.matrixHTML(["CH32V003F4P6"], true).note;
  check("正規化名での検索が当たらない", /^[1-9]/.test(hit), hit);
  ui.search = "";
}

// 4. 型番に無い instance の薄表示（G12）。CH32V303CBT6 の USART は3つ。
{
  const absent = api.absentInstances("CH32V303CBT6");
  check("薄表示すべき instance が出ない", absent.has("USART8"), [...absent.keys()].join());
  check("持っている instance まで薄くしている",
        !absent.has("USART1") && !absent.has("USART3"), [...absent.keys()].join());
  // V30x の I2S は 2 と 3 しか無く（I2S1 が無い）、数は 2。番号で切ると誤る。
  check("番号で切って正しい I2S3 を消している",
        !api.absentInstances("CH32V307VCT6").has("I2S3"),
        [...api.absentInstances("CH32V307VCT6").keys()].join());
}

// 5. chip 未指定・未知はどちらも選択画面（G8）。既定の chip を勝手に開かない。
{
  ui.chip = "";
  check("chip 未指定で選択画面にならない", api.selection().mode === "chooser",
        api.selection().mode);
  ui.chip = "CH32V999";
  check("知らない chip で選択画面にならない", api.selection().mode === "chooser",
        api.selection().mode);
  ui.chip = "";
}

// 6. 比較表の見出しは資料の崩れを畳んで出す（G5）。
{
  const labels = [...api.comparisonHTML(
    api.state.products.filter(p => p.series === "CH32V003"))
    .matchAll(/<td class="label">([^<]*)<\/td>/g)].map(m => m[1]);
  check("折り返しで割れたハイフンが残っている",
        !labels.some(l => /\w-\s/.test(l)), labels.join(" / "));
  check("固定列と同じ値の行を重ねて出している",
        !labels.some(l => /^General-purpose I\/O$/.test(l)), labels.join(" / "));
}

if (bad.length) {
  console.error(`pins.html の表示が壊れています（${bad.length} 件）:`);
  for (const line of bad) console.error("  - " + line);
  process.exit(1);
}
console.error("pins.html: 表示の不変量 6 件すべて満たしています");
