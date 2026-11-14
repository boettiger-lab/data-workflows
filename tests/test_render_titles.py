"""Tests for scripts/render-titles.py."""
import importlib.util
import pathlib
import unittest

_SRC = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "render-titles.py"
_spec = importlib.util.spec_from_file_location("render_titles", _SRC)
rt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rt)


class RenderTitle(unittest.TestCase):
    def test_live_shapes(self):
        cases = {
            "Fallback: MTBS burn severity 1984 (CONUS, 30 m COG)": "MTBS burn severity 1984 (CONUS, 30 m)",
            "Fallback: Mangrove extent 1985 (cloud-optimized GeoTIFF, ~30 m)": "Mangrove extent 1985 (~30 m)",
            "Fallback: Wildfire Hazard Potential 2023 — classified, CONUS — WGS84 COG":
                "Wildfire Hazard Potential 2023 — classified, CONUS",
            "Fallback: Burn Probability (Alaska) cloud-optimized GeoTIFF": "Burn Probability (Alaska)",
            "Fallback: Fuel Vegetation Cover 2024, cloud-optimized GeoTIFF, 30 m": "Fuel Vegetation Cover 2024, 30 m",
            "Fallback: CAL FIRE FVEG — CWHR 13-class major habitat types — categorical COG (WGS84, 30 m)":
                "CAL FIRE FVEG — CWHR 13-class major habitat types",
            "Fallback: LANDFIRE 2024 Existing Vegetation Type (CONUS, 30 m) (WGS84 COG)":
                "LANDFIRE 2024 Existing Vegetation Type (CONUS, 30 m)",
            "Fallback: Copernicus DEM GLO-90 global COG (90 m, EPSG:4326)": "Copernicus DEM GLO-90 global (90 m)",
            "Fallback: Sea Floor Aspect (sine component) cloud-optimized GeoTIFF (WGS84, 0.05 degrees)":
                "Sea Floor Aspect (sine component) (0.05 degrees)",
            "Fallback: California Climate Zones COG (WGS84)": "California Climate Zones",
            "Fallback: Daily salinity for 2020-12-28": "Daily salinity for 2020-12-28",
        }
        for old, new in cases.items():
            self.assertEqual(rt.render_title(old), new)

    def test_format_only_takes_collection_title(self):
        self.assertEqual(rt.render_title("Fallback: Cloud-optimized GeoTIFF (EPSG:4326)", "RCN"), "RCN")

    def test_retitle_touches_fallbacks_only_and_is_idempotent(self):
        d = {"title": "C", "renders": {"a": {"title": "Fallback: X (COG)"}, "b": {"title": "Y (COG)"}}}
        self.assertEqual(len(rt.retitle(d)), 1)
        self.assertEqual(d["renders"]["a"]["title"], "X")
        self.assertEqual(d["renders"]["b"]["title"], "Y (COG)")
        self.assertEqual(rt.retitle(d), [])


if __name__ == "__main__":
    unittest.main()
