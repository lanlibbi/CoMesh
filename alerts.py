"""
Alerting router for supply monitoring.
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import SupplyAlert, GpuNode
import os
import yaml

log = logging.getLogger("gpu-pool.alerts")

router = APIRouter(prefix="/alerts", tags=["alerts"])

# Load configuration
CONFIG_PATH = os.environ.get("CONFIG_PATH", "/app/config.yaml")
if not os.path.exists(CONFIG_PATH):
    # Local dev fallback
    CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")

def load_config():
    try:
        with open(CONFIG_PATH, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        log.warning(f"Could not load config from {CONFIG_PATH}: {e}")
        return {}

config = load_config()

# Default threshold if not in config
SUPPLY_CHECK_THRESHOLD = config.get('supply_check_threshold', 20)

class SupplyAlertOut(BaseModel):
    id: int
    node_id: int
    supply_type: str
    supply_name: str
    level_percent: int
    threshold_percent: int
    alert_triggered: bool
    alert_sent_at: Optional[str]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True

@router.get("/supplies", response_model=List[SupplyAlertOut])
def get_supply_alerts(db: Session = Depends(get_db)):
    """Get all supply alerts."""
    alerts = db.query(SupplyAlert).order_by(SupplyAlert.created_at.desc()).all()
    return alerts

def check_and_create_supply_alerts(db: Session):
    """
    Check supplies for all nodes and create alerts if below threshold.
    Implements debounce: max 1 alert per supply per 24h.
    """
    # In a real implementation, we would get supply levels from nodes.
    # For now, we simulate by checking if there are any nodes and creating a test alert.
    # This is a placeholder and should be replaced with actual supply data from nodes.
    
    nodes = db.query(GpuNode).filter(GpuNode.is_enabled == True).all()
    if not nodes:
        log.warning("No nodes found, skipping supply check")
        return
    
    # For demonstration, we'll create a test alert for the first node if none exists for today
    # In reality, we would iterate over each supply type for each node.
    node = nodes[0]
    
    # Check if we already have an alert for this node and supply type in the last 24h
    supply_type = "toner"
    supply_name = "black_toner"
    twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
    
    existing_alert = db.query(SupplyAlert).filter(
        SupplyAlert.node_id == node.id,
        SupplyAlert.supply_type == supply_type,
        SupplyAlert.supply_name == supply_name,
        SupplyAlert.created_at >= twenty_four_hours_ago
    ).first()
    
    if existing_alert:
        log.info(f"Recent alert exists for node {node.id} {supply_type}/{supply_name}, skipping due to debounce")
        return
    
    # Simulate a low supply level (e.g., 15% which is below threshold of 20%)
    level_percent = 15
    threshold_percent = SUPPLY_CHECK_THRESHOLD
    
    if level_percent <= threshold_percent:
        alert = SupplyAlert(
            node_id=node.id,
            supply_type=supply_type,
            supply_name=supply_name,
            level_percent=level_percent,
            threshold_percent=threshold_percent,
            alert_triggered=True,
            alert_sent_at=None  # Email sending would be implemented here
        )
        db.add(alert)
        db.commit()
        log.info(f"Created supply alert for node {node.id}: {supply_type}/{supply_name} at {level_percent}%")
    else:
        log.info(f"Supply level OK for node {node.id}: {supply_type}/{supply_name} at {level_percent}%")

# Background task to run supply checks periodically
# In a production setup, you might use a proper scheduler like APScheduler or Celery.
# For simplicity, we'll expose an endpoint to trigger the check and suggest running it via cron or external scheduler.

@router.post("/check", status_code=204)
def trigger_supply_check(db: Session = Depends(get_db)):
    """Manually trigger a supply check (for testing)."""
    check_and_create_supply_alerts(db)
    return