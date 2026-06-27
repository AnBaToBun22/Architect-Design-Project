const camera = document.getElementById("camera");
const canvas = document.getElementById("snapshot");
const startCameraButton = document.getElementById("startCamera");
const captureButton = document.getElementById("capture");
const scanForm = document.getElementById("scanForm");
const resultBox = document.getElementById("scanResult");
const uploadImageInput = document.getElementById("uploadImage");
const triggerUploadButton = document.getElementById("triggerUpload");
const scanButton = document.getElementById("scanButton");

let imageData = "";
let stream = null;

function formatListType(type) {
  if (type === "blacklist") return "Danh sách đen";
  if (type === "whitelist") return "Danh sách trắng";
  return "Chưa xác định";
}

async function startCamera() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" } },
      audio: false,
    });
    camera.hidden = false;
    canvas.hidden = true;
    camera.srcObject = stream;
  } catch (error) {
    resultBox.hidden = false;
    resultBox.className = "result blacklist";
    resultBox.textContent = "Không thể truy cập camera. Hãy cấp quyền camera hoặc chạy bằng HTTPS/localhost.";
  }
}

function captureFrame() {
  if (!camera.videoWidth) {
    resultBox.hidden = false;
    resultBox.className = "result blacklist";
    resultBox.textContent = "Camera chưa sẵn sàng.";
    return;
  }

  canvas.width = camera.videoWidth;
  canvas.height = camera.videoHeight;
  const context = canvas.getContext("2d");
  context.drawImage(camera, 0, 0, canvas.width, canvas.height);
  imageData = canvas.toDataURL("image/jpeg", 0.85);
  resultBox.hidden = false;
  resultBox.className = "result ok";
  resultBox.textContent = "Đã chụp ảnh. Bấm Quét biển số để hệ thống tự nhận diện.";
}

async function submitScan(event) {
  event.preventDefault();
  const plateInput = document.getElementById("plateNumber");
  const plateNumber = plateInput.value;
  const location = document.getElementById("location").value;

  scanButton.disabled = true;
  scanButton.textContent = "Đang quét...";
  resultBox.hidden = false;
  resultBox.className = "result ok";
  resultBox.textContent = "Đang nhận diện biển số và kiểm tra danh sách...";

  try {
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

    if (data.ok) {
      plateInput.value = data.plate_number;
      const source = data.recognized_by_ocr ? "OCR tự đọc" : "Biển số nhập tay";
      resultBox.textContent = `${data.message} ${source}: ${data.plate_number} | Loại: ${formatListType(data.list_type)}`;
      imageData = "";
      uploadImageInput.value = "";
    } else {
      resultBox.textContent = data.message;
    }
  } catch (error) {
    resultBox.hidden = false;
    resultBox.className = "result blacklist";
    resultBox.textContent = "Không thể gửi ảnh lên máy chủ. Vui lòng thử lại.";
  } finally {
    scanButton.disabled = false;
    scanButton.textContent = "Quét biển số";
  }
}

triggerUploadButton.addEventListener("click", () => {
  uploadImageInput.click();
});

uploadImageInput.addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (!file) return;

  const reader = new FileReader();

  reader.onload = (e) => {
    imageData = e.target.result;

    const img = new Image();
    img.onload = () => {
      camera.hidden = true;
      canvas.hidden = false;

      canvas.width = img.width;
      canvas.height = img.height;
      const context = canvas.getContext("2d");
      context.drawImage(img, 0, 0, canvas.width, canvas.height);

      resultBox.hidden = false;
      resultBox.className = "result ok";
      resultBox.textContent = "Đã tải ảnh từ thiết bị. Bấm Quét biển số để hệ thống tự nhận diện.";
    };
    img.src = imageData;
  };

  reader.readAsDataURL(file);
});

startCameraButton.addEventListener("click", startCamera);
captureButton.addEventListener("click", captureFrame);
scanForm.addEventListener("submit", submitScan);
