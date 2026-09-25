"""Home Assistant integration routes."""
from fastapi import APIRouter, HTTPException

from models.request_models import HAAutomationAddRequest, HAConfigUpdateRequest


def setup_homeassistant_routes(ha_manager) -> APIRouter:
    router = APIRouter()

    @router.get("/ha/status")
    async def get_ha_status():
        """Get Home Assistant integration status"""
        return ha_manager.get_status()

    @router.get("/ha/config")
    async def get_ha_config():
        """Get Home Assistant configuration (token masked)"""
        return ha_manager.get_config()

    @router.put("/ha/config")
    async def update_ha_config(request: HAConfigUpdateRequest):
        """Update Home Assistant connection settings"""
        return await ha_manager.update_config(
            ha_url=request.ha_url,
            ha_token=request.ha_token,
            entity_id=request.entity_id,
            enabled=request.enabled,
        )

    @router.post("/ha/test")
    async def test_ha_connection():
        """Test Home Assistant connection"""
        return await ha_manager.test_connection()

    @router.get("/ha/automations")
    async def get_ha_automations():
        """List all automation rules"""
        return {"automations": ha_manager.automations}

    @router.post("/ha/automations")
    async def add_ha_automations(request: HAAutomationAddRequest):
        """Add automation rules"""
        ha_manager.add_automations([rule.model_dump() for rule in request.rules])
        return {
            "message": f"Added {len(request.rules)} rule(s)",
            "automations": ha_manager.automations,
        }

    @router.delete("/ha/automations/{index}")
    async def delete_ha_automation(index: int):
        """Remove an automation rule by index"""
        removed = ha_manager.remove_automation(index)
        if removed is None:
            raise HTTPException(status_code=404, detail=f"Automation index {index} not found")
        return {
            "message": f"Removed automation rule",
            "removed": removed,
            "automations": ha_manager.automations,
        }

    @router.post("/ha/push-state")
    async def force_push_state():
        """Force immediate state push to Home Assistant"""
        if not ha_manager.enabled:
            raise HTTPException(status_code=400, detail="HA integration not enabled")
        await ha_manager.notify_state_change()
        return {
            "message": "State pushed",
            "state": ha_manager.last_pushed_state,
        }

    @router.post("/ha/script/{script_id}")
    async def trigger_ha_script(script_id: str):
        """Trigger a Home Assistant script by ID"""
        if not ha_manager.ha_url or not ha_manager.ha_token:
            raise HTTPException(status_code=400, detail="HA not configured")
        await ha_manager.call_ha_script(script_id)
        return {"message": f"Script '{script_id}' triggered"}

    return router
