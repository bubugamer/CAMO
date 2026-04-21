const params = new URLSearchParams(window.location.search);
window.CamoDemo.updateSharedLinks(
  params.get("project_id") || "",
  params.get("name") || "",
  params.get("character_id") || "",
);
