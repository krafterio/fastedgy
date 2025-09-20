# Logger

**Simple console logging with configurable log levels**

The Logger provides basic console logging management with configurable log levels to control which messages are displayed during development and production.

## Available Exports

- `LOG_LEVELS`: Constants for log levels (NONE, ERROR, WARNING, INFO, DEBUG)
- `initializeLogger(logLevel)`: Configure console log level filtering
- `logger`: Simple wrapper object around console methods

## Log Levels

```javascript
import { LOG_LEVELS } from 'vue-fastedgy/utils/logger'

console.log(LOG_LEVELS)
// {
//   NONE: 'none',
//   ERROR: 'error',
//   WARNING: 'warning',
//   INFO: 'info',
//   DEBUG: 'debug'
// }
```

**Level Hierarchy:**
- `NONE`: No console output at all
- `ERROR`: Only console.error() works
- `WARNING`: console.error() + console.warn() work
- `INFO`: console.error() + console.warn() + console.info() + console.log() work
- `DEBUG`: All console methods work (including console.debug())

## Initialize Logger

```javascript
import { initializeLogger, LOG_LEVELS } from 'vue-fastedgy/utils/logger'

// Set log level (overwrites native console methods)
initializeLogger(LOG_LEVELS.INFO)

// Now console methods are filtered based on level
console.debug('This will not appear') // Filtered out
console.info('This will appear')      // Allowed
console.error('This will appear')     // Allowed

// Production: disable all logging
initializeLogger(LOG_LEVELS.NONE)
console.error('This will not appear') // All console output disabled
```

## Logger Object

Simple wrapper that delegates to console methods:

```javascript
import { logger } from 'vue-fastedgy/utils/logger'

// These are just wrappers around console methods
logger.error('Error message')   // Same as console.error()
logger.warn('Warning message')  // Same as console.warn()
logger.info('Info message')     // Same as console.info()
logger.log('Log message')       // Same as console.log()
logger.debug('Debug message')   // Same as console.debug()
```

## How It Works

The logger works by overwriting the native `console` methods when `initializeLogger()` is called. It doesn't add complex features like formatting or transports - it simply enables/disables console output based on the configured level.

**Important:** Once you call `initializeLogger()`, the native console methods are permanently modified for the session.

## Get Started

Ready to configure logging in your application? Check out the setup guide:

[Setup Guide](setup.md){ .md-button .md-button--primary }
