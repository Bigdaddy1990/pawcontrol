from __future__ import annotations

from datetime import datetime
from math import atan2, cos, radians, sin, sqrt
from typing import Any, Dict

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .gps_settings import GPSSettingsStore


def _device_id_from_dog(hass: HomeAssistant, dog_id: str | None) -> str | None:
    if not dog_id:
        return None
    dev_reg = dr.async_get(hass)
    # identifiers contain tuples like (DOMAIN, dog_id)
    for dev in dev_reg.devices.values():
        if dev.identifiers and any(
            idt[0] == DOMAIN and idt[1] == dog_id for idt in dev.identifiers
        ):
            return dev.id
    return None


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a)) if a > 1 else 2 * atan2(sqrt(a), sqrt(1 - a))
    # correct formula recompute
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


def _now() -> datetime:
    return dt_util.utcnow()


def _inc_state(hass, entity_id: str, inc: float, attrs: dict | None = None):
    st = hass.states.get(entity_id)
    try:
        val = (
            float(st.state)
            if st and st.state not in ("unknown", "unavailable")
            else 0.0
        )
    except Exception:
        val = 0.0
    newv = (val + inc) if isinstance(inc, float) else (int(val) + int(inc))
    try:
        # integers where appropriate (e.g. seconds)
        if isinstance(inc, float):
            newv = round(newv, 1)
        else:
            newv = int(newv)
    except Exception:
        pass
    hass.states.async_set(entity_id, newv, attrs or {})


class PawControlGPSHandler:
    """GPS handler providing walk tracking, dispatcher updates, and safe-zone events."""

    def __init__(self, hass: HomeAssistant, options: dict[str, Any]):
        self.hass = hass
        self.options = options or {}
        self.entry_id: str | None = None
        self._routes: Dict[str, Dict[str, Any]] = {}
        self._metrics: Dict[str, Dict[str, Any]] = {}
        self._settings_store: GPSSettingsStore | None = None
        self._settings: dict[str, Any] = {}
        self._safe_status: Dict[str, Dict[str, Any]] = {}

    async def async_setup(self) -> None:
        self._settings_store = GPSSettingsStore(
            self.hass, self.entry_id or "default", DOMAIN
        )
        self._settings = await self._settings_store.async_load()
        # Merge options.safe_zones if present
        try:
            opt_sz = (self.options or {}).get("safe_zones") or {}
            if opt_sz:
                base = dict(self._settings or {})
                base.setdefault("safe_zones", {})
                base["safe_zones"].update(opt_sz)
                self._settings = base
                await self._settings_store.async_save(self._settings)
        except Exception:
            pass

    def _dog_id(self, dog_id: str | None) -> str:
        if dog_id:
            return dog_id
        dogs = (self.options or {}).get("dogs") or []
        if dogs and isinstance(dogs, list):
            return dogs[0].get("dog_id") or dogs[0].get("name") or "dog"
        return "dog"

    def _get(self, dog: str) -> Dict[str, Any]:
        st = self._routes.setdefault(
            dog, {"active": False, "start": None, "points": [], "distance_m": 0.0}
        )
        self._metrics.setdefault(
            dog, {"points_total": 0, "points_dropped": 0, "acc_sum": 0.0}
        )
        self._safe_status.setdefault(
            dog,
            {
                "inside": None,
                "last_ts": None,
                "enters": 0,
                "leaves": 0,
                "time_today": 0.0,
            },
        )
        return st

    async def async_start_walk(
        self, walk_type: str | None = None, dog_id: str | None = None
    ) -> None:
        dog = self._dog_id(dog_id)
        st = self._get(dog)
        st.update({"active": True, "start": _now(), "points": [], "distance_m": 0.0})
        self.hass.bus.async_fire(
            "pawcontrol_walk_started",
            {"dog_id": dog, "walk_type": walk_type or "normal"},
        )
        self.hass.states.async_set(
            f"sensor.{DOMAIN}_{dog}_walk_started", _now().isoformat()
        )

    async def async_end_walk(
        self,
        rating: int | None = None,
        notes: str | None = None,
        dog_id: str | None = None,
    ) -> None:
        dog = self._dog_id(dog_id)
        st = self._get(dog)
        end = _now()
        duration_s = (
            (end - (st.get("start") or end)).total_seconds() if st.get("start") else 0.0
        )
        dist_m = float(st.get("distance_m") or 0.0)
        avg_kmh = (dist_m / 1000.0) / (duration_s / 3600.0) if duration_s > 0 else 0.0
        self.hass.states.async_set(
            f"sensor.{DOMAIN}_{dog}_walk_distance_last",
            round(dist_m, 1),
            {"unit_of_measurement": "m"},
        )
        self.hass.states.async_set(
            f"sensor.{DOMAIN}_{dog}_walk_duration_last",
            int(duration_s),
            {"unit_of_measurement": "s"},
        )
        self.hass.states.async_set(
            f"sensor.{DOMAIN}_{dog}_walk_avg_speed_last",
            round(avg_kmh, 2),
            {"unit_of_measurement": "km/h"},
        )
        self.hass.bus.async_fire(
            "pawcontrol_walk_finished",
            {
                "dog_id": dog,
                "distance_m": dist_m,
                "duration_s": duration_s,
                "avg_speed_kmh": avg_kmh,
                "rating": rating,
                "notes": notes,
            },
        )
        self.hass.bus.async_fire(
            "pawcontrol_route_summary",
            {
                "dog_id": dog,
                "distance_m": dist_m,
                "duration_s": duration_s,
                "points": len(st.get("points") or []),
            },
        )
        st["active"] = False
        # Persist route summary
        try:
            from .route_store import RouteHistoryStore

            store = RouteHistoryStore(
                self.hass, getattr(self, "entry_id", "default"), DOMAIN
            )
            await store.async_add_walk(
                self.hass,
                getattr(self, "entry_id", "default"),
                DOMAIN,
                dog,
                st.get("start").isoformat() if st.get("start") else None,
                end.isoformat(),
                dist_m,
                duration_s,
                len(st.get("points") or []),
                limit=int(
                    (
                        ((self.options or {}).get("advanced") or {}).get(
                            "route_history_limit"
                        )
                        or 500
                    )
                ),
            )
        except Exception:
            pass

    async def async_update_location(
        self,
        latitude: float,
        longitude: float,
        accuracy: float | None = None,
        source: str | None = None,
        dog_id: str | None = None,
    ) -> None:
        dog = self._dog_id(dog_id)
        st = self._get(dog)
        now_iso = _now().isoformat()
        inc = 0.0
        pts = st["points"]
        if pts:
            lat0, lon0, ts0 = pts[-1]
            inc = _haversine_m(lat0, lon0, latitude, longitude)
        st["points"].append((latitude, longitude, now_iso))
        st["distance_m"] = float(st.get("distance_m") or 0.0) + inc
        if st.get("active"):
            self.hass.states.async_set(
                f"sensor.{DOMAIN}_{dog}_walk_distance_current",
                round(st["distance_m"], 1),
                {"unit_of_measurement": "m"},
            )
        # daily counters
        if st.get("paused"):
            # Still dispatch to tracker & events, but don't accumulate stats
            async_dispatcher_send(
                self.hass, f"{DOMAIN}_gps_update_{dog}", latitude, longitude, accuracy
            )
            self.hass.bus.async_fire(
                "pawcontrol_route_point",
                {
                    "dog_id": dog,
                    "lat": latitude,
                    "lon": longitude,
                    "acc": accuracy,
                    "ts": now_iso,
                },
            )
            return

        # continue with accumulation
        if inc > 0:
            _inc_state(
                self.hass,
                f"sensor.{DOMAIN}_{dog}_walk_distance_today",
                inc,
                {"unit_of_measurement": "m"},
            )
        # duration accumulation
        try:
            if len(pts) >= 1:
                from datetime import datetime as _dt

                t_prev = (
                    _dt.fromisoformat(pts[-1][2].replace("Z", "+00:00"))
                    if isinstance(pts[-1][2], str)
                    else None
                )
                t_now = _now()
                if t_prev:
                    ds = (t_now - t_prev).total_seconds()
                    if st.get("active") and ds > 0:
                        _inc_state(
                            self.hass,
                            f"sensor.{DOMAIN}_{dog}_walk_time_today",
                            ds,
                            {"unit_of_measurement": "s"},
                        )
        except Exception:
            pass
        # dispatcher to device_tracker
        async_dispatcher_send(
            self.hass, f"{DOMAIN}_gps_update_{dog}", latitude, longitude, accuracy
        )
        self.hass.bus.async_fire(
            "pawcontrol_route_point",
            {
                "dog_id": dog,
                "lat": latitude,
                "lon": longitude,
                "acc": accuracy,
                "ts": now_iso,
            },
        )
        # GPS metrics
        try:
            mt = self._metrics.get(dog) or {
                "points_total": 0,
                "points_dropped": 0,
                "acc_sum": 0.0,
            }
            mt["points_total"] = int(mt.get("points_total", 0)) + 1
            if accuracy is not None:
                mt["acc_sum"] = float(mt.get("acc_sum", 0.0)) + float(accuracy)
                avg = mt["acc_sum"] / max(1, mt["points_total"])
                self.hass.states.async_set(
                    f"sensor.{DOMAIN}_{dog}_gps_accuracy_avg", round(avg, 1)
                )
            self.hass.states.async_set(
                f"sensor.{DOMAIN}_{dog}_gps_points_total", int(mt["points_total"])
            )
            self._metrics[dog] = mt
        except Exception:
            pass
        # Safe zone evaluation
        try:
            z = (self._settings or {}).get("safe_zones", {}).get(dog) or {}
            if z:
                cz_lat = float(z.get("latitude"))
                cz_lon = float(z.get("longitude"))
                radius = float(z.get("radius", 50))
                enable_alerts = bool(z.get("enable_alerts", True))
                dist = _haversine_m(cz_lat, cz_lon, latitude, longitude)
                inside = dist <= radius
                now_dt = _now()
                stz = self._safe_status.setdefault(
                    dog,
                    {
                        "inside": None,
                        "last_ts": now_dt,
                        "enters": 0,
                        "leaves": 0,
                        "time_today": 0.0,
                    },
                )
                prev_inside = stz.get("inside")
                # accumulate time when previously inside
                if stz.get("last_ts"):
                    delta = (now_dt - stz["last_ts"]).total_seconds()
                    if prev_inside is True and delta > 0:
                        stz["time_today"] = float(stz.get("time_today", 0.0)) + float(
                            delta
                        )
                # transition counters
                if prev_inside is not None and inside != prev_inside:
                    if inside:
                        stz["enters"] = int(stz.get("enters", 0)) + 1
                    else:
                        stz["leaves"] = int(stz.get("leaves", 0)) + 1
                stz["inside"] = inside
                stz["last_ts"] = now_dt
                # publish metrics
                self.hass.states.async_set(
                    f"sensor.{DOMAIN}_{dog}_time_in_safe_zone_today",
                    int(stz.get("time_today", 0.0)),
                    {"unit_of_measurement": "s"},
                )
                self.hass.states.async_set(
                    f"sensor.{DOMAIN}_{dog}_safe_zone_enters_today",
                    int(stz.get("enters", 0)),
                )
                self.hass.states.async_set(
                    f"sensor.{DOMAIN}_{dog}_safe_zone_leaves_today",
                    int(stz.get("leaves", 0)),
                )
                # dispatch to binary_sensor
                async_dispatcher_send(
                    self.hass,
                    f"pawcontrol_safe_zone_update_{dog}",
                    inside,
                    dist,
                    radius,
                )
                # events on transition
                if prev_inside is not None and inside != prev_inside and enable_alerts:
                    evt = (
                        "pawcontrol_safe_zone_entered"
                        if inside
                        else "pawcontrol_safe_zone_left"
                    )
                    self.hass.bus.async_fire(
                        evt, {"dog_id": dog, "distance_m": dist, "radius_m": radius}
                    )
                    device_id = _device_id_from_dog(self.hass, dog)
                    action = "entered" if inside else "exited"
                    zone_name = str(z.get("name") or "safe_zone")
                    self.hass.bus.async_fire(
                        "pawcontrol_geofence_alert",
                        {
                            "device_id": device_id,
                            "dog_id": dog,
                            "action": action,
                            "zone": zone_name,
                            "distance_m": dist,
                            "radius_m": radius,
                        },
                    )
        except Exception:
            pass


async def async_pause_tracking(self, dog_id: str | None = None) -> None:
    dog = self._dog_id(dog_id)
    st = self._get(dog)
    st["paused"] = True
    # expose state for UI/debug
    self.hass.states.async_set(f"sensor.{DOMAIN}_{dog}_gps_tracking_paused", True)


async def async_resume_tracking(self, dog_id: str | None = None) -> None:
    dog = self._dog_id(dog_id)
    st = self._get(dog)
    st["paused"] = False
    self.hass.states.async_set(f"sensor.{DOMAIN}_{dog}_gps_tracking_paused", False)

    async def async_export_last_route(
        self, dog_id: str | None = None, fmt: str = "geojson", to_media: bool = False
    ) -> str | None:
        import json
        import os

        dog = self._dog_id(dog_id)
        st = self._get(dog)
        base = (
            self.hass.config.path("media/pawcontrol_routes")
            if to_media
            else self.hass.config.path("pawcontrol_routes")
        )
        os.makedirs(base, exist_ok=True)
        if fmt == "geojson":
            feat = {
                "type": "Feature",
                "properties": {"dog_id": dog},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[p[1], p[0]] for p in (st.get("points") or [])],
                },
            }
            data = {"type": "FeatureCollection", "features": [feat]}
            path = os.path.join(base, f"{dog}_last_route.geojson")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            return path
        elif fmt == "gpx":
            path = os.path.join(base, f"{dog}_last_route.gpx")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('<?xml version="1.0"?><gpx version="1.1"></gpx>')
            return path
        return None

    async def async_generate_diagnostics(self, dog_id: str | None = None) -> str | None:
        import json
        import os

        dog = self._dog_id(dog_id)
        base = self.hass.config.path("pawcontrol_diagnostics")
        os.makedirs(base, exist_ok=True)
        st = self._get(dog)
        out = {
            "dog_id": dog,
            "active": st.get("active"),
            "distance_m": st.get("distance_m"),
            "points": st.get("points")[-500:],
            "options": self.options,
        }
        path = os.path.join(base, f"{dog}_diagnostics.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
        return path

    async def async_reset_gps_stats(self, dog_id: str | None = None) -> None:
        dog = self._dog_id(dog_id)
        self._metrics[dog] = {"points_total": 0, "points_dropped": 0, "acc_sum": 0.0}
        try:
            self.hass.states.async_set(f"sensor.{DOMAIN}_{dog}_gps_points_total", 0)
            self.hass.states.async_set(f"sensor.{DOMAIN}_{dog}_gps_points_dropped", 0)
            self.hass.states.async_set(f"sensor.{DOMAIN}_{dog}_gps_accuracy_avg", None)
        except Exception:
            pass


# Hook: after each location post, fire device-scoped event
async def _hook_post_location(hass, dog_id: str):
    try:
        from . import _fire_device_event

        _fire_device_event(hass, "gps_location_posted", dog_id)
    except Exception:
        pass
