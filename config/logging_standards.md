# Logging Standards Documentation

## Overview
This document defines the logging standards that agents should follow when adding logging to code.

## Log Levels

| Level | When to Use |
|-------|-------------|
| DEBUG | Detailed diagnostic information |
| INFO | General operational events |
| WARNING | Unexpected but recoverable situations |
| ERROR | Error events that allow continued operation |
| CRITICAL | Severe errors causing program termination |

## Required Logging Points

### 1. Function Entry/Exit
- Log at DEBUG level when entering and exiting functions
- Include function name and key parameters

### 2. External API Calls
- Log at INFO level before making external calls
- Log response status and time taken
- Log at ERROR level if the call fails

### 3. Database Operations
- Log at INFO level for all database operations
- Include operation type (SELECT, INSERT, UPDATE, DELETE)
- Log at ERROR level for failures

### 4. Exception Handling
- Log at ERROR level in catch blocks
- Include exception type and message
- Include stack trace for unexpected exceptions

## Code Examples

### Python
```python
import logging

logger = logging.getLogger(__name__)

def process_data(data: dict) -> dict:
    logger.debug(f"Entering process_data with {len(data)} items")
    try:
        # Processing logic
        result = transform(data)
        logger.info(f"Successfully processed {len(result)} items")
        return result
    except ValueError as e:
        logger.error(f"Validation error in process_data: {e}")
        raise
    finally:
        logger.debug("Exiting process_data")
```

### C#
```csharp
using Microsoft.Extensions.Logging;

public class DataProcessor
{
    private readonly ILogger<DataProcessor> _logger;

    public DataProcessor(ILogger<DataProcessor> logger)
    {
        _logger = logger;
    }

    public async Task<Result> ProcessAsync(Data data)
    {
        _logger.LogDebug("Entering ProcessAsync with {ItemCount} items", data.Count);
        try
        {
            var result = await TransformAsync(data);
            _logger.LogInformation("Successfully processed {ResultCount} items", result.Count);
            return result;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error processing data");
            throw;
        }
    }
}
```

## Structured Logging Format
Use structured logging with named parameters:
- Good: `logger.info("User {user_id} logged in from {ip_address}", user_id, ip)`
- Bad: `logger.info(f"User {user_id} logged in from {ip}")`
