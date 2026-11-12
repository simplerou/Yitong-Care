"""Optional MCP stdio transport; no arbitrary Cypher tool."""
from mcp.server.fastmcp import FastMCP
from app.operations.contracts import CheckRequest
from validation_service.config import ValidationSettings
from validation_service.main import facts
from validation_service.rules import evaluate
mcp=FastMCP('Heling rule validation')
@mcp.tool()
def validate_medication(payload:dict)->dict:
    """Check doses and ingredient conflicts; never prescribe or persist."""
    request=CheckRequest.model_validate(payload)
    if request.kind!='medication':raise ValueError('medication contract required')
    return evaluate(request,facts(ValidationSettings()))
@mcp.tool()
def validate_nutrition(payload:dict)->dict:
    """Check numeric nutrition targets, allergens and food-drug conflicts."""
    request=CheckRequest.model_validate(payload)
    if request.kind not in ('menu','meal_swap'):raise ValueError('nutrition contract required')
    return evaluate(request,facts(ValidationSettings()))
if __name__=='__main__':mcp.run(transport='stdio')
