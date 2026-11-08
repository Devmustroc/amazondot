"""
Homelab SRE intents for Proxmox VE status and Docker container monitoring.
Requires adult/admin role (protected by RBAC).
"""
from typing import AsyncGenerator
from core_server.intents.base import BaseIntent, IntentContext, intent
from core_server import homelab_tools


@intent
class ProxmoxStatusIntent(BaseIntent):
    name = "proxmox_status"
    priority = 20
    requires_admin = True

    def can_handle(self, ctx: IntentContext) -> bool:
        p = ctx.prompt.lower()
        return any(k in p for k in ["état du serveur", "etat du serveur", "serveur proxmox", "état de proxmox", "etat de proxmox", "statut proxmox", "charge du serveur", "comment va le serveur", "santé du serveur"])

    async def execute(self, ctx: IntentContext) -> AsyncGenerator[str, None]:
        reply = await homelab_tools.get_proxmox_status_spoken()
        yield reply


@intent
class ProxmoxClusterIntent(BaseIntent):
    name = "proxmox_cluster"
    priority = 20
    requires_admin = True

    def can_handle(self, ctx: IntentContext) -> bool:
        p = ctx.prompt.lower()
        return any(k in p for k in ["machines virtuelles", "combien de vm", "liste des vm", "liste des conteneurs lxc", "ressources du cluster"])

    async def execute(self, ctx: IntentContext) -> AsyncGenerator[str, None]:
        reply = await homelab_tools.get_cluster_resources_spoken()
        yield reply


@intent
class DockerStatusIntent(BaseIntent):
    name = "docker_status"
    priority = 20
    requires_admin = True

    def can_handle(self, ctx: IntentContext) -> bool:
        p = ctx.prompt.lower()
        return any(k in p for k in ["conteneurs docker", "état de docker", "etat de docker", "conteneurs tournent", "liste des conteneurs", "docker sur ct", "tourne mamitales", "état de mamitales", "etat de mamitales", "mamitales tourne", "état de immich", "etat de immich", "immich tourne", "état de vaultwarden", "etat de vaultwarden", "vaultwarden tourne"])

    async def execute(self, ctx: IntentContext) -> AsyncGenerator[str, None]:
        p = ctx.prompt.lower()
        c_name = None
        if "mamitales" in p:
            c_name = "mamitales-backend"
        elif "immich" in p:
            c_name = "immich_server"
        elif "vaultwarden" in p or "mots de passe" in p:
            c_name = "vaultwarden"

        reply = await homelab_tools.get_docker_status_spoken(container_name=c_name)
        yield reply
