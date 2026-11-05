// Shows the saved answers in data.json. Every piece of text goes in with textContent, every class
// comes from the fixed tables below and never from the data, and the only links are built here
// from an advisory or CVE ID, to two fixed addresses. Nothing is ever set as HTML.
(function () {
  "use strict";

  var ID = /^(GHSA(-[0-9a-z]{4}){3}|CVE-\d{4}-\d{4,})$/;
  var QUESTION_ID = /^[a-z]{2}-\d{3}$/;
  var BASES = {
    ghsa: "https://github.com/advisories/",
    cve: "https://nvd.nist.gov/vuln/detail/"
  };
  var SOURCES = { ghsa: "GitHub advisory", nvd: "NVD record", kev: "CISA KEV entry" };
  var TYPES = {
    lookup: "Look up", version: "Version", multihop: "Several records",
    disagree: "Sources disagree", abstain: "Should decline"
  };
  var CHECKS = {
    passed: "Passed", repaired: "Passed after cutting an ID", abstained: "The model declined",
    refused: "Refused", parse_failure: "Reply not readable", stopped: "Reply stopped early"
  };
  var CLAIMS = {
    passed: ["Passed", "right"], failed: ["Failed", "wrong"], unverifiable: ["Cannot check", "neutral"]
  };

  function element(tag, text, className) {
    var node = document.createElement(tag);
    if (text !== undefined && text !== null) node.textContent = String(text);
    if (className) node.className = className;
    return node;
  }

  function own(table, key) {
    return typeof key === "string" && Object.prototype.hasOwnProperty.call(table, key) ? table[key] : null;
  }

  function linkFor(id) {
    if (typeof id !== "string" || !ID.test(id)) return null;
    var link = element("a", id);
    link.href = (id.indexOf("GHSA-") === 0 ? BASES.ghsa : BASES.cve) + id;
    link.rel = "noopener noreferrer";
    link.target = "_blank";
    return link;
  }

  function badge(label, kind) {
    return element("span", label, "badge " + kind);
  }

  function outcomeBadge(entry) {
    var outcome = entry && entry.outcome;
    var said = entry && entry.declined ? ": declined" : "";
    if (outcome === "correct") return badge("Right" + said, "right");
    if (outcome === "wrong") return badge("Wrong" + said, "wrong");
    return badge("Not scored", "neutral");
  }

  function renderView(parent, view) {
    var box = element("div", null, "answer");
    if (!view || typeof view !== "object") return box;
    var heading = view.state === "answer" ? "Otis answered"
      : view.state === "declined" ? "Otis did not answer" : "Problem";
    box.appendChild(element("h4", heading));
    if (view.verdict === "yes" || view.verdict === "no") {
      box.appendChild(element("p", view.verdict === "yes" ? "Yes." : "No.", "verdict"));
    }
    if (view.value) box.appendChild(element("p", view.value, "value"));
    if (view.explanation) box.appendChild(element("p", view.explanation, "explanation"));
    if (view.sources_differ && view.scores) {
      box.appendChild(element("p", "GitHub and NVD differ. GitHub: " + (view.scores.github || "none") +
        ". NVD: " + (view.scores.nvd || "none") + ".", "differ"));
    }
    if (Array.isArray(view.ids) && view.ids.length) {
      var list = element("ul", null, "records");
      view.ids.forEach(function (id) {
        var item = element("li");
        item.appendChild(linkFor(id) || element("span", id));
        list.appendChild(item);
      });
      box.appendChild(list);
    }
    parent.appendChild(box);
  }

  function renderClaims(parent, claims) {
    if (!Array.isArray(claims) || !claims.length) return;
    var list = element("ul", null, "claims");
    claims.forEach(function (claim) {
      var item = element("li");
      var found = own(CLAIMS, claim && claim.status) || ["Unknown", "neutral"];
      item.appendChild(badge(found[0], found[1]));
      item.appendChild(element("span", " " + (claim && claim.claim), "claim"));
      if (claim && claim.reason) item.appendChild(element("p", claim.reason, "reason"));
      list.appendChild(item);
    });
    parent.appendChild(element("h5", "Each claim, checked against the records"));
    parent.appendChild(list);
  }

  function renderChecked(parent, title, entry, note) {
    var section = element("section", null, "result");
    var head = element("div", null, "result-head");
    head.appendChild(element("h3", title));
    head.appendChild(outcomeBadge(entry));
    section.appendChild(head);
    if (note) {
      section.appendChild(element("p", note, "same"));
    } else {
      renderView(section, entry.view);
      if (entry.verdict !== null) {
        var line = "Checker: " + (own(CHECKS, entry.verdict) || "Unknown");
        if (typeof entry.rule === "number") line += " at rule " + entry.rule;
        section.appendChild(element("p", line, "check"));
      }
      if (Array.isArray(entry.reasons)) {
        entry.reasons.forEach(function (reason) { section.appendChild(element("p", reason, "reason")); });
      }
      renderClaims(section, entry.claims);
    }
    parent.appendChild(section);
  }

  function sameResult(a, b) {
    return JSON.stringify([a.verdict, a.rule, a.view]) === JSON.stringify([b.verdict, b.rule, b.view]);
  }

  function renderRecords(parent, question, records) {
    var shown = Array.isArray(question.shown) ? question.shown : [];
    parent.appendChild(element("h3", "The " + shown.length + " records Otis was shown"));
    var list = element("ul", null, "shown");
    shown.forEach(function (unitId) {
      var entry = records && Object.prototype.hasOwnProperty.call(records, unitId) ? records[unitId] : null;
      if (!entry) return;
      var item = element("li");
      var top = element("p", null, "record-top");
      top.appendChild(linkFor(entry.id) || element("span", entry.id));
      top.appendChild(element("span", " " + (own(SOURCES, entry.source) || "Record"), "source"));
      item.appendChild(top);
      item.appendChild(element("p", entry.header, "header"));
      item.appendChild(element("p", entry.excerpt, "excerpt"));
      list.appendChild(item);
    });
    parent.appendChild(list);
  }

  function renderQuestion(container, data, question) {
    container.replaceChildren();
    if (!question || typeof question !== "object") return;
    var type = own(TYPES, question.type) || "Question";
    container.appendChild(element("p", type + " · " + question.id, "kicker"));
    container.appendChild(element("h2", question.question));
    var gold = element("p", null, "gold");
    gold.appendChild(element("strong", "Gold answer. "));
    gold.appendChild(element("span", question.gold && question.gold.text));
    container.appendChild(gold);
    if (question.gold && question.gold.derivation) {
      container.appendChild(element("p", question.gold.derivation, "derivation"));
    }
    var results = element("div", null, "results");
    renderChecked(results, "The model alone", { outcome: question.raw.outcome, declined: question.raw.declined,
      view: question.raw.view, verdict: null, rule: null, reasons: [], claims: [] }, null);
    renderChecked(results, "Checked, Phase 5 checker", question.phase5, null);
    var same = sameResult(question.phase5, question.phase6);
    renderChecked(results, "Checked, Phase 6 checker", question.phase6,
      same ? "Same result as the Phase 5 checker." : null);
    container.appendChild(results);
    renderRecords(container, question, data.records);
    var cost = typeof question.cost_usd === "number" ? "$" + question.cost_usd.toFixed(3) : "unknown";
    var seconds = typeof question.latency_s === "number" ? question.latency_s.toFixed(1) + " s" : "unknown";
    container.appendChild(element("p", "This reply cost " + cost + " and took " + seconds + ".", "cost"));
  }

  function renderSummary(container, meta) {
    container.replaceChildren();
    var rows = [["The model alone", "raw"], ["Checked, Phase 5 checker", "phase5"], ["Checked, Phase 6 checker", "phase6"]];
    rows.forEach(function (row) {
      var found = meta && meta.totals && meta.totals[row[1]];
      var box = element("div", null, "stat");
      box.appendChild(element("span", found ? found.correct + " of " + found.of : "n/a", "figure"));
      box.appendChild(element("span", row[0], "label"));
      container.appendChild(box);
    });
  }

  function short(hash) {
    return typeof hash === "string" ? hash.slice(0, 7) : "unknown";
  }

  function renderSystems(container, meta) {
    var systems = (meta && meta.systems) || {};
    container.textContent = "The replies were saved at commit " + short(meta && meta.run_commit) +
      ". The Phase 5 checker is the tag phase5-system-v1 (" + short(systems["phase5-system-v1"]) +
      "). The Phase 6 checker is the tag phase6-system-v1 (" + short(systems["phase6-system-v1"]) +
      "), run over the same saved replies with no new model call. Run 1 of 3 is shown.";
  }

  function renderList(container, data, onPick) {
    container.replaceChildren();
    data.questions.forEach(function (question) {
      var item = element("li");
      var button = element("button", null, "pick");
      button.type = "button";
      button.appendChild(element("span", question.id, "pick-id"));
      button.appendChild(element("span", question.question, "pick-text"));
      var marks = element("span", null, "pick-marks");
      ["phase5", "phase6"].forEach(function (key) {
        var mark = question[key] && question[key].outcome === "correct" ? "right"
          : question[key] && question[key].outcome === "wrong" ? "wrong" : "neutral";
        marks.appendChild(element("span", null, "dot " + mark));
      });
      button.appendChild(marks);
      button.addEventListener("click", function () { onPick(question); });
      item.appendChild(button);
      container.appendChild(item);
    });
  }

  window.OtisReplay = {
    renderQuestion: renderQuestion, renderList: renderList, renderSummary: renderSummary,
    renderSystems: renderSystems
  };

  var detail = document.getElementById("detail");
  if (!detail) return;
  fetch("data.json")
    .then(function (response) { return response.json(); })
    .then(function (data) {
      renderSummary(document.getElementById("summary"), data.meta);
      renderSystems(document.getElementById("systems"), data.meta);
      function show(question) {
        renderQuestion(detail, data, question);
        if (QUESTION_ID.test(question.id)) window.location.hash = question.id;
      }
      renderList(document.getElementById("list"), data, function (question) {
        show(question);
        // On a phone the answer sits below the list, so bring it into view.
        if (window.matchMedia("(max-width: 44rem)").matches) detail.scrollIntoView({ block: "start" });
      });
      var wanted = window.location.hash.slice(1);
      var start = QUESTION_ID.test(wanted) ? data.questions.filter(function (q) { return q.id === wanted; })[0] : null;
      show(start || data.questions[0]);
    })
    .catch(function () {
      detail.replaceChildren(element("p", "The saved answers could not be loaded. Serve this folder with " +
        "python -m http.server and open it from there."));
    });
})();
