document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("jobForm");
  const availableJobs = document.getElementById("availableJobs");
  const inProgressJobs = document.getElementById("inProgressJobs");
  const completedJobs = document.getElementById("completedJobs");
  const acceptModal = document.getElementById("acceptModal");
  const confirmAccept = document.getElementById("confirmAccept");
  const cancelAccept = document.getElementById("cancelAccept");

  let currentJobId = null;

  async function loadJobs() {
    try {
      const res = await fetch("/api/jobs");
      const jobs = await res.json();

      if (availableJobs) availableJobs.innerHTML = "";
      if (inProgressJobs) inProgressJobs.innerHTML = "";
      if (completedJobs) completedJobs.innerHTML = "";

      jobs.forEach(job => {
        if (job.status === "AVAILABLE" && availableJobs) {
          availableJobs.appendChild(createJobCard(job, "available"));
        } else if (job.status === "IN_PROGRESS" && inProgressJobs) {
          inProgressJobs.appendChild(createJobCard(job, "inProgress"));
        } else if (job.status === "COMPLETED" && completedJobs) {
          completedJobs.appendChild(createJobCard(job, "completed"));
        }
      });
    } catch (err) {
      console.error("Error loading jobs:", err);
    }
  }

  function createJobCard(job, type) {
    const div = document.createElement("div");
    div.className = "job-card";

    const customerInfo = type === "available"
      ? `<p class="text-gray-400 italic">Customer info hidden until accepted</p>`
      : `<p><strong>Customer:</strong> ${job.customer_name}</p><p><strong>Phone:</strong> ${job.customer_phone}</p>`;

    const waiterInfo = job.waiter_name
      ? `<p><strong>Waiter:</strong> ${job.waiter_name}</p><p><strong>Phone:</strong> ${job.waiter_phone}</p>`
      : "";

    div.innerHTML = `
      <h3 class="text-lg mb-1">${job.description}</h3>
      ${customerInfo}
      <p><strong>Time:</strong> ${job.dateTime}</p>
      <p><strong>Cost:</strong> ${job.costVND} VND (~$${job.costUSD})</p>
      ${job.note ? `<p><strong>Note:</strong> ${job.note}</p>` : ""}
      <p><strong>Status:</strong> 
        <span class="font-medium ${
          job.status === "AVAILABLE" ? "text-green-600" :
          job.status === "IN_PROGRESS" ? "text-yellow-600" :
          "text-gray-500"
        }">${job.status}</span>
      </p>
      ${waiterInfo}
    `;

    const btn = document.createElement("button");
    btn.className = "btn-primary w-full mt-3";

    if (type === "available") {
      btn.textContent = "Accept Job";
      btn.onclick = () => openAcceptModal(job.id);
    } else if (type === "inProgress") {
      btn.textContent = "Mark as Done";
      btn.onclick = () => completeJob(job.id);
    } else {
      btn.textContent = "Completed";
      btn.disabled = true;
      btn.classList.add("opacity-50");
    }

    div.appendChild(btn);
    return div;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(form).entries());
    const res = await fetch("/api/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });
    const result = await res.json();
    alert(result.message || result.error);
    form.reset();
    loadJobs();
  });

  function openAcceptModal(id) {
    currentJobId = id;
    acceptModal.classList.remove("hidden");
  }

  cancelAccept.addEventListener("click", () => {
    acceptModal.classList.add("hidden");
  });

  confirmAccept.addEventListener("click", async () => {
    const waiter_name = document.getElementById("waiter_name").value.trim();
    const waiter_phone = document.getElementById("waiter_phone").value.trim();
    if (!waiter_name || !waiter_phone) return alert("Please fill all fields");

    const res = await fetch("/api/accept", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: currentJobId, waiter_name, waiter_phone })
    });
    const result = await res.json();
    alert(result.message || result.error);
    acceptModal.classList.add("hidden");
    loadJobs();
  });

  async function completeJob(id) {
    const res = await fetch("/api/complete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id })
    });
    const data = await res.json();
    alert(data.message || data.error);
    loadJobs();
  }

  loadJobs();
});
