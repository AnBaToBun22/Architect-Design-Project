const alertBox = document.getElementById("alertBox");
const logsTable = document.getElementById("logsTable");

function getLatestLogId() {
  const firstRow = logsTable.querySelector("tbody tr");
  return firstRow ? Number(firstRow.dataset.id || 0) : 0;
}

let latestId = getLatestLogId();

function addAlert(item) {
  alertBox.hidden = false;
  alertBox.textContent = `Cảnh báo danh sách đen: phát hiện xe ${item.plate_number} tại ${item.location || "vị trí chưa xác định"}.`;

  const row = document.createElement("tr");
  row.dataset.id = item.id;
  row.innerHTML = `
    <td>${item.id}</td>
    <td>${item.plate_number}</td>
    <td><span class="tag blacklist">Danh sách đen</span></td>
    <td>${item.location || "-"}</td>
    <td>${item.police_name || "-"}</td>
    <td>${String(item.created_at).slice(0, 19).replace("T", " ")}</td>
  `;
  logsTable.querySelector("tbody").prepend(row);
}

async function pollNotifications() {
  const response = await fetch(`/api/notifications?after_id=${latestId}`);
  if (!response.ok) return;

  const items = await response.json();
  if (!items.length) return;

  items.reverse().forEach((item) => {
    latestId = Math.max(latestId, item.id);
    addAlert(item);
  });
}

setInterval(pollNotifications, 5000);
