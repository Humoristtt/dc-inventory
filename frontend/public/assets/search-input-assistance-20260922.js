(() => {
  "use strict";

  const selector =
    'input[placeholder="Имя, username или Telegram ID"]';

  function configure(input) {
    input.setAttribute("autocomplete", "off");
    input.setAttribute("autocorrect", "off");
    input.setAttribute("autocapitalize", "off");
    input.setAttribute("spellcheck", "false");
    input.setAttribute("data-gramm", "false");
    input.setAttribute("data-gramm_editor", "false");

    input.spellcheck = false;
    input.autocomplete = "off";
  }

  function apply(root) {
    if (root.matches?.(selector)) {
      configure(root);
    }

    root.querySelectorAll?.(selector).forEach(configure);
  }

  apply(document);

  new MutationObserver((records) => {
    for (const record of records) {
      for (const node of record.addedNodes) {
        if (node.nodeType === 1) {
          apply(node);
        }
      }
    }
  }).observe(document.documentElement, {
    childList: true,
    subtree: true
  });

  document.addEventListener(
    "focusin",
    (event) => {
      if (event.target.matches?.(selector)) {
        configure(event.target);
      }
    },
    true
  );
})();
