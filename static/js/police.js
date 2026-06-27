const camera = document.getElementById("camera");
const canvas = document.getElementById("snapshot");
const startCameraButton = document.getElementById("startCamera");
const captureButton = document.getElementById("capture");
const scanForm = document.getElementById("scanForm");
const resultBox = document.getElementById("scanResult");

let imageData = "";
let stream = null;

async function startCamera() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" } },
      audio: false,
    });
    camera.srcObject = stream;
  } catch (error) {
    resultBox.hidden = false;
    resultBox.className = "result blacklist";
    resultBox.textContent = "Cannot access camera. Please allow camera permission or use HTTPS/localhost.";
  }
}

function captureFrame() {
  if (!camera.videoWidth) {
    resultBox.hidden = false;
    resultBox.className = "result blacklist";
    resultBox.textContent = "Camera is not ready yet.";
    return;
  }

  canvas.width = camera.videoWidth;
  canvas.height = camera.videoHeight;
  const context = canvas.getContext("2d");
  context.drawImage(camera, 0, 0, canvas.width, canvas.height);
  imageData = canvas.toDataURL("image/jpeg", 0.85);
  resultBox.hidden = false;
  resultBox.className = "result ok";
  resultBox.textContent = "Image captured. Enter or confirm the plate number, then submit.";
}

async function submitScan(event) {
  event.preventDefault();
  const plateNumber = document.getElementById("plateNumber").value;
  const location = document.getElementById("location").value;

  const response = await fetch("/api/scan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      plate_number: plateNumber,
      location,
      image_data: imageData,
    }),
  });

  const data = await response.json();
  resultBox.hidden = false;
  resultBox.className = data.is_blacklist ? "result blacklist" : "result ok";
  resultBox.textContent = data.ok
    ? `${data.message} Plate: ${data.plate_number} | Type: ${data.list_type}`
    : data.message;

  if (data.ok) {
    scanForm.reset();
    imageData = "";
  }
}

startCameraButton.addEventListener("click", startCamera);
captureButton.addEventListener("click", captureFrame);
scanForm.addEventListener("submit", submitScan);
