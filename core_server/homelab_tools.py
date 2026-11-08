"""
Homelab SRE Tools for TAD Core.
Provides secure read-only monitoring and status inspection for Proxmox VE cluster and Docker containers.
"""
import os
import json
import logging
import asyncio
from typing import Dict, Any, Optional
from core_server import config

logger = logging.getLogger("homelab_tools")


async def run_ssh_pve(remote_cmd: str, timeout: float = 3.5) -> Optional[str]:
    """Executes a non-blocking read-only command on the Proxmox VE host via SSH."""
    if not os.path.exists(config.PROXMOX_SSH_KEY):
        logger.warning("SSH key not found at %s", config.PROXMOX_SSH_KEY)
        return None

    cmd = [
        "ssh",
        "-i", config.PROXMOX_SSH_KEY,
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=2",
        "-o", "StrictHostKeyChecking=accept-new",
        f"{config.PROXMOX_SSH_USER}@{config.PROXMOX_HOST}",
        remote_cmd,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        if proc.returncode == 0:
            return stdout.decode(errors="replace").strip()
        logger.warning("SSH command failed (code %d): %s", proc.returncode, stderr.decode(errors="replace").strip())
        return None
    except asyncio.TimeoutError:
        logger.warning("SSH command timed out on Proxmox host %s", config.PROXMOX_HOST)
        return None
    except Exception as e:
        logger.error("SSH execution error: %s", e)
        return None


async def get_proxmox_status() -> Dict[str, Any]:
    """Retrieves live node status metrics (CPU, RAM, load, uptime) from Proxmox VE."""
    raw_json = await run_ssh_pve("pvesh get nodes/pve/status --output-format json")
    if not raw_json:
        return {"online": False, "error": f"Hôte Proxmox ({config.PROXMOX_HOST}) injoignable"}

    try:
        data = json.loads(raw_json)
        cpu_model = data.get("cpuinfo", {}).get("model", "AMD")
        cores = data.get("cpuinfo", {}).get("cores", 0)
        load_1m = data.get("loadavg", ["0.00"])[0]

        mem_info = data.get("memory", {})
        mem_total = mem_info.get("total", 0) / (1024 ** 3)
        mem_used = mem_info.get("used", 0) / (1024 ** 3)
        mem_pct = (mem_used / mem_total * 100) if mem_total else 0

        uptime_min = data.get("uptime", 0) // 60
        uptime_str = f"{uptime_min // 60}h {uptime_min % 60}m" if uptime_min >= 60 else f"{uptime_min} minutes"

        return {
            "online": True,
            "host": config.PROXMOX_HOST,
            "cpu_model": cpu_model,
            "cores": cores,
            "loadavg_1m": load_1m,
            "memory_used_gb": round(mem_used, 1),
            "memory_total_gb": round(mem_total, 1),
            "memory_pct": round(mem_pct),
            "uptime": uptime_str,
            "pve_version": data.get("pveversion", "9.x"),
        }
    except Exception as e:
        logger.error("Failed to parse Proxmox status json: %s", e)
        return {"online": False, "error": f"Erreur de parsing des métriques: {e}"}


async def get_proxmox_status_spoken() -> str:
    """Returns a natural French summary of Proxmox VE status optimized for voice playback."""
    metrics = await get_proxmox_status()
    if not metrics.get("online"):
        return f"Le serveur Proxmox à l'adresse {config.PROXMOX_HOST} est actuellement injoignable."

    return (
        f"Le serveur Proxmox est en ligne avec {metrics['cores']} cœurs. "
        f"Charge CPU à {metrics['loadavg_1m']}, mémoire vive à {metrics['memory_pct']}% "
        f"soit {metrics['memory_used_gb']} sur {metrics['memory_total_gb']} gigas, "
        f"et un temps de fonctionnement de {metrics['uptime']}."
    )


async def get_cluster_resources() -> Dict[str, Any]:
    """Retrieves the list of active VMs and LXC containers on the Proxmox cluster."""
    raw_json = await run_ssh_pve("pvesh get cluster/resources --output-format json")
    if not raw_json:
        return {"online": False, "error": f"Hôte Proxmox ({config.PROXMOX_HOST}) injoignable"}

    try:
        items = json.loads(raw_json)
        running_vms = [i["name"] for i in items if i.get("type") == "qemu" and i.get("status") == "running"]
        running_lxcs = [i["name"] for i in items if i.get("type") == "lxc" and i.get("status") == "running"]

        return {
            "online": True,
            "running_vms": running_vms,
            "running_lxcs": running_lxcs,
            "vms_count": len(running_vms),
            "lxcs_count": len(running_lxcs),
        }
    except Exception as e:
        logger.error("Failed to parse cluster resources json: %s", e)
        return {"online": False, "error": f"Erreur de parsing des ressources: {e}"}


async def get_cluster_resources_spoken() -> str:
    """Returns a spoken French summary of the running VMs and LXC containers."""
    res = await get_cluster_resources()
    if not res.get("online"):
        return f"Impossible de contacter le cluster Proxmox à l'adresse {config.PROXMOX_HOST}."

    vms_str = ", ".join(res["running_vms"]) if res["running_vms"] else "aucune"
    lxcs_str = ", ".join(res["running_lxcs"]) if res["running_lxcs"] else "aucun"

    return (
        f"Le cluster compte {res['vms_count']} machines virtuelles actives dont {vms_str}, "
        f"et {res['lxcs_count']} conteneurs LXC dont {lxcs_str}."
    )


async def get_docker_status(container_name: Optional[str] = None) -> Dict[str, Any]:
    """Inspects running Docker containers on CT 105 (docker-host)."""
    raw_output = await run_ssh_pve("pct exec 105 -- docker ps --format '{{.Names}}|{{.Status}}|{{.Image}}'")
    if not raw_output:
        return {"online": False, "error": "Conteneur hôte Docker (CT 105) injoignable"}

    lines = [line.strip() for line in raw_output.split("\n") if line.strip()]
    containers = []
    for line in lines:
        parts = line.split("|")
        if len(parts) >= 2:
            containers.append({
                "name": parts[0],
                "status": parts[1],
                "image": parts[2] if len(parts) > 2 else "",
            })

    if container_name:
        c_clean = container_name.lower().strip()
        matched = [c for c in containers if c_clean in c["name"].lower()]
        return {
            "online": True,
            "queried_name": container_name,
            "found": len(matched) > 0,
            "matches": matched,
            "total_running": len(containers),
        }

    running_names = [c["name"] for c in containers if "up" in c["status"].lower()]
    highlighted = [n for n in ["mamitales-backend", "ollama", "caddy-caddy-1", "paperless-webserver", "immich_server", "vaultwarden"] if n in running_names]

    return {
        "online": True,
        "total_running": len(running_names),
        "highlighted": highlighted,
        "all_containers": running_names,
    }


async def get_docker_status_spoken(container_name: Optional[str] = None) -> str:
    """Returns a concise spoken French response regarding Docker container health."""
    data = await get_docker_status(container_name=container_name)
    if not data.get("online"):
        return "Le conteneur hôte Docker n'est pas accessible sur le cluster."

    if container_name:
        if data.get("found"):
            m = data["matches"][0]
            return f"Le conteneur {m['name']} est bien en cours d'exécution avec le statut {m['status']}."
        return f"Je n'ai trouvé aucun conteneur en cours d'exécution correspondant à {container_name}."

    hl_str = ", ".join(data.get("highlighted", []))
    return f"{data['total_running']} conteneurs Docker tournent sur le cluster, dont {hl_str}."
