const form = document.getElementById("signup-form");
const status = document.getElementById("status");
const submitBtn = document.getElementById("submit-btn");

const API_BASE = window.__BIFOCAL_API__ || "/api/signup"; // adjust via embedding script if needed

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  status.textContent = "Submitting…";
  status.className = "";
  submitBtn.disabled = true;

  const formData = new FormData(form);
  const payload = Object.fromEntries(formData.entries());
  payload.beta = formData.get("beta") === "on";

  try {
    const response = await fetch(API_BASE, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error("Request failed");
    }

    status.textContent = "Thanks! We'll be in touch soon.";
    status.className = "success";
    form.reset();
  } catch (err) {
    console.error(err);
    status.textContent = "Something went wrong. Please try again.";
    status.className = "error";
  } finally {
    submitBtn.disabled = false;
  }
});
