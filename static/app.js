const form = document.getElementById("calc-form");
const output = document.getElementById("output");

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const payload = {
    a: parseFloat(document.getElementById("a").value),
    b: parseFloat(document.getElementById("b").value),
    operator: document.getElementById("operator").value,
  };

  try {
    const response = await fetch("/api/calculate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();

    if (response.ok) {
      output.textContent = `Result: ${data.result}`;
      output.className = "success";
    } else {
      output.textContent = data.error || "Something went wrong.";
      output.className = "error";
    }
  } catch {
    output.textContent = "Could not reach the server.";
    output.className = "error";
  }
});
