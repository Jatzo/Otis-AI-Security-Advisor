// The search behind the replay page. It has no page code in it, so Node can load it for tests.
//
// The word splitting must give the same words as SQLite FTS5 with the tokenizer "unicode61
// remove_diacritics 2", because the ranking is only the real one if the words are the real ones. ASCII is handled here: letters and digits are words, lower-cased, and
// everything else ends a word. For any other character the page uses the fold table that
// scripts/build_search_index.py asked SQLite for, so no Unicode rule is copied by hand. A table
// value is the text the character becomes inside a word (empty when a diacritic is dropped), and
// null when the character ends a word.

(function (root) {
  "use strict";

  function tokenize(text, fold) {
    var words = [];
    var current = "";
    for (var character of text) {
      var code = character.codePointAt(0);
      var piece = null;
      if (code < 128) {
        if ((code >= 48 && code <= 57) || (code >= 97 && code <= 122)) {
          piece = character;
        } else if (code >= 65 && code <= 90) {
          piece = character.toLowerCase();
        }
      } else if (Object.prototype.hasOwnProperty.call(fold, character)) {
        piece = fold[character];
      }
      if (piece === null) {
        if (current !== "") {
          words.push(current);
          current = "";
        }
      } else {
        current += piece;
      }
    }
    if (current !== "") {
      words.push(current);
    }
    return words;
  }

  var api = { tokenize: tokenize };
  root.OtisSearch = Object.assign(root.OtisSearch || {}, api);
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(globalThis);
