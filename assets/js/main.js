/* AI 产品经理作品集：最小交互脚本（无依赖） */
(function () {
  "use strict";

  // 移动端导航
  var toggle = document.querySelector(".nav-toggle");
  var nav = document.getElementById("site-nav");
  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      toggle.textContent = open ? "收起" : "菜单";
    });
  }

  // 当前年份（页脚兜底）
  var yearEls = document.querySelectorAll("[data-year]");
  for (var j = 0; j < yearEls.length; j++) {
    yearEls[j].textContent = String(new Date().getFullYear());
  }
})();
