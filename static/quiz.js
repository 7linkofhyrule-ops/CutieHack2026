const form = document.getElementById("quiz");
    const error = document.getElementById("cuisine-error");

    function checkedCount() {
      return form.querySelectorAll('input[name="cuisine"]:checked').length;
    }

    // Show the number next to each slider and fill the track up to the thumb
    form.querySelectorAll('input[type="range"]').forEach(function (slider) {
      const out = document.getElementById(slider.id + "-out");
      function update() {
        out.textContent = slider.value;
        const pct = ((slider.value - slider.min) / (slider.max - slider.min)) * 100;
        slider.style.background =
          "linear-gradient(to right, #003DA5 " + pct + "%, #CDD7EA " + pct + "%)";
      }
      slider.addEventListener("input", update);
      update();
    });

    // Require at least two cuisines
    form.addEventListener("submit", function (e) {
      if (checkedCount() < 2) {
        e.preventDefault();
        error.hidden = false;
      }
    });

    form.addEventListener("change", function () {
      if (checkedCount() >= 2) error.hidden = true;
    });