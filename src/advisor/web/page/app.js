// Shows what the server sends. Every piece of text goes in with textContent, and the only links
// are built here from an advisory or CVE ID, to two fixed addresses. Nothing is ever set as HTML.
(function () {
  "use strict";

  var ID = /^(GHSA(-[0-9a-z]{4}){3}|CVE-\d{4}-\d{4,})$/;
  var BASES = {
    ghsa: "https://github.com/advisories/",
    cve: "https://nvd.nist.gov/vuln/detail/"
  };

  function element(tag, text, className) {
    var node = document.createElement(tag);
    if (text !== undefined && text !== null) node.textContent = String(text);
    if (className) node.className = className;
    return node;
  }

  function linkFor(id) {
    if (typeof id !== "string" || !ID.test(id)) return null;
    var link = element("a", id);
    link.href = (id.indexOf("GHSA-") === 0 ? BASES.ghsa : BASES.cve) + id;
    link.rel = "noopener noreferrer";
    link.target = "_blank";
    return link;
  }

  function render(container, view) {
    container.replaceChildren();
    if (!view || typeof view !== "object") return;
    var heading = view.state === "answer" ? "Otis found" : view.state === "declined" ? "No answer" : "Problem";
    container.appendChild(element("h2", heading));
    if (view.verdict === "yes" || view.verdict === "no") {
      container.appendChild(element("p", view.verdict === "yes" ? "Yes." : "No.", "verdict"));
    }
    if (view.value) container.appendChild(element("p", view.value, "value"));
    if (view.explanation) container.appendChild(element("p", view.explanation, "explanation"));
    if (view.sources_differ && view.scores) {
      var scores = element("p", "GitHub and NVD differ. GitHub: " + (view.scores.github || "none") +
        ". NVD: " + (view.scores.nvd || "none") + ".", "differ");
      container.appendChild(scores);
    }
    if (Array.isArray(view.ids) && view.ids.length) {
      var list = element("ul", null, "records");
      view.ids.forEach(function (id) {
        var item = element("li");
        var link = linkFor(id);
        item.appendChild(link || element("span", id));
        list.appendChild(item);
      });
      container.appendChild(list);
    }
  }

  window.OtisPage = { render: render };

  var form = document.getElementById("ask-form");
  if (!form) return;
  var box = document.getElementById("question");
  var out = document.getElementById("answer");
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: box.value })
    })
      .then(function (response) { return response.json(); })
      .then(function (data) { render(out, data); })
      .catch(function () {
        render(out, { state: "error", explanation: "Otis could not be reached. Try again in a moment." });
      });
  });
})();
