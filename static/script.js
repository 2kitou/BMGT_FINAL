document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("jobForm");
  const availableJobs = document.getElementById("availableJobs");
  const inProgressJobs = document.getElementById("inProgressJobs");
  const completedJobs = document.getElementById("completedJobs");

  const acceptModal = document.getElementById("acceptModal");
  const confirmAccept = document.getElementById("confirmAccept");
  const cancelAccept = document.getElementById("cancelAccept");

  const feedbackModal = document.getElementById("feedbackModal");
  const confirmFeedback = document.getElementById("confirmFeedback");
  const cancelFeedback = document.getElementById("cancelFeedback");
  const stars = document.querySelectorAll(".star");
  const feedbackText = document.getElementById("feedbackText");

  let currentJobId = null;
  let currentRating = 0;

  // ---------- COST LOGIC ----------
  const VND_PER_ITEM = 5000;
  const USD_PER_ITEM = 0.20;
  let currentCurrency = "VND";

  const quantityInput = document.getElementById("quantityInput");
  const costDisplay = document.getElementById("costDisplay");
  const costVNDHidden = document.getElementById("costVND");
  const toggleCurrencyBtn = document.getElementById("toggleCurrency");

  function updateCost() {
    const qty = Number(quantityInput.value) || 1;
    const totalVND = qty * VND_PER_ITEM;
    const totalUSD = qty * USD_PER_ITEM;

    if (currentCurrency === "VND") {
      costDisplay.value = `${totalVND.toLocaleString()} VND`;
    } else {
      costDisplay.value = `$${totalUSD.toFixed(2)} USD`;
    }

    costVNDHidden.value = totalVND; // backend always receives VND
  }

  quantityInput.addEventListener("input", updateCost);

  toggleCurrencyBtn.addEventListener("click", () => {
    currentCurrency = currentCurrency === "VND" ? "USD" : "VND";
    toggleCurrencyBtn.textContent = currentCurrency;
    updateCost();
  });

  updateCost(); // initialize
  // ---------- END COST LOGIC ----------

  async function loadJobs() {
    try {
      const res = await fetch("/api/jobs");
      const jobs = await res.json();

      availableJobs.innerHTML = "";
      inProgressJobs.innerHTML = "";
      completedJobs.innerHTML = "";

      jobs.forEach(job => {
        const card = createJobCard(job);
        if (job.status === "AVAILABLE") availableJobs.appendChild(card);
        else if (job.status === "IN_PROGRESS") inProgressJobs.appendChild(card);
        else completedJobs.appendChild(card);
      });
    } catch (err) {
      console.error("Error loading jobs:", err);
    }
  }

  function createJobCard(job) {
    const div = document.createElement("div");
    div.className = "job-card";

    const qty = job.quantity ? ` × ${job.quantity}` : "";
    const customerInfo = job.status === "AVAILABLE"
      ? `<p class="text-gray-400 italic">Customer info hidden until accepted</p>`
      : `<p><strong>Customer:</strong> ${job.customer_name}</p><p><strong>Phone:</strong> ${job.customer_phone}</p>`;

    const ratingHtml = job.rating
      ? `<p><strong>Rating:</strong> ${"⭐".repeat(Number(job.rating))} (${job.rating})</p><p class="text-sm italic">${job.feedback || ""}</p>`
      : "";

    div.innerHTML = `
      <h3 class="text-lg mb-1">${job.description}${qty}</h3>
      ${customerInfo}
      <p><strong>Time:</strong> ${job.dateTime || ""}</p>
      <p><strong>Cost:</strong> ${job.costVND} VND (~$${job.costUSD})</p>
      ${job.note ? `<p><strong>Note:</strong> ${job.note}</p>` : ""}
      <p><strong>Status:</strong> <span class="font-medium ${
        job.status === "AVAILABLE"
          ? "text-green-600"
          : job.status === "IN_PROGRESS"
          ? "text-yellow-600"
          : "text-gray-500"
      }">${job.status}</span></p>
      ${ratingHtml}
    `;

    const btn = document.createElement("button");
    btn.className = "btn-primary w-full mt-3";

    if (job.status === "AVAILABLE") {
      btn.textContent = "Accept Job";
      btn.onclick = () => openAcceptModal(job.id);
    } else if (job.status === "IN_PROGRESS") {
      btn.textContent = "Mark as Done";
      btn.onclick = () => openFeedbackModal(job.id);
    } else {
      btn.textContent = "Completed";
      btn.disabled = true;
      btn.classList.add("opacity-60");
    }

    div.appendChild(btn);
    return div;
  }

  // ---------- SUBMIT ----------
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(form).entries());

    // ensure quantity integer >= 1
    data.quantity = Number(data.quantity || 1);
    if (!Number.isInteger(data.quantity) || data.quantity < 1) {
      return alert("Quantity must be a positive integer.");
    }

    try {
      const res = await fetch("/api/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data)
      });
      const result = await res.json();
      alert(result.message || result.error);
      form.reset();
      updateCost();
      loadJobs();
    } catch (err) {
      console.error(err);
      alert("Failed to submit job.");
    }
  });

  // ---------- ACCEPT ----------
  function openAcceptModal(id) {
    currentJobId = id;
    acceptModal.classList.remove("hidden");
    document.getElementById("waiter_name").value = "";
    document.getElementById("waiter_phone").value = "";
  }

  cancelAccept.addEventListener("click", () => {
    acceptModal.classList.add("hidden");
    currentJobId = null;
  });

  confirmAccept.addEventListener("click", async () => {
    const waiter_name = document.getElementById("waiter_name").value.trim();
    const waiter_phone = document.getElementById("waiter_phone").value.trim();
    if (!waiter_name || !waiter_phone) return alert("Please enter name and phone.");

    try {
      const res = await fetch("/api/accept", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: currentJobId, waiter_name, waiter_phone })
      });
      const result = await res.json();
      alert(result.message || result.error);
      acceptModal.classList.add("hidden");
      loadJobs();
    } catch (err) {
      console.error(err);
      alert("Failed to accept job.");
    }
  });

  // ---------- FEEDBACK ----------
  function openFeedbackModal(id) {
    currentJobId = id;
    currentRating = 0;
    feedbackText.value = "";
    stars.forEach(s => s.classList.remove("text-yellow-400"));
    feedbackModal.classList.remove("hidden");
  }

  cancelFeedback.addEventListener("click", () => {
    feedbackModal.classList.add("hidden");
    currentJobId = null;
    currentRating = 0;
  });

  stars.forEach(star => {
    star.addEventListener("click", () => {
      const val = Number(star.getAttribute("data-value"));
      currentRating = val;
      stars.forEach(s => {
        const v = Number(s.getAttribute("data-value"));
        s.classList.toggle("text-yellow-400", v <= val);
      });
    });
  });

  confirmFeedback.addEventListener("click", async () => {
    const feedback = feedbackText.value.trim();
    try {
      const res = await fetch("/api/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: currentJobId, rating: currentRating || null, feedback })
      });
      const data = await res.json();
      alert(data.message || data.error);
      feedbackModal.classList.add("hidden");
      currentJobId = null;
      currentRating = 0;
      loadJobs();
    } catch (err) {
      console.error(err);
      alert("Failed to submit feedback.");
    }
  });

  loadJobs();
});
