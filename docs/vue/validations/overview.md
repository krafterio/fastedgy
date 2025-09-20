# Validations

**Format Pydantic validation errors into readable text**

The Validations utility provides a single helper function to format validation errors from FastEdgy APIs (Pydantic) into user-friendly error messages.

## Available Function

- `formatValidationErrors(error, defaultMessage)`: Format Pydantic validation errors to readable text

## Key Features

- **Pydantic Error Formatting**: Convert FastEdgy/Pydantic errors to readable messages
- **Multiple Error Handling**: Handle arrays of validation errors
- **Field Location Mapping**: Show field paths (e.g., "body → email")
- **Fallback Messages**: Use default message when error details unavailable

## Function Signature

```javascript
formatValidationErrors(error, defaultMessage = undefined)
```

**Parameters:**
- `error`: Error object from API request with `data.detail` property
- `defaultMessage`: Optional default message (defaults to "Erreur inconnue")

**Returns:**
- `string`: Formatted error message
- `undefined`: If no error details found

## Quick Example

```javascript
import { formatValidationErrors } from 'vue-fastedgy/utils/validations'

// Single error
const singleError = {
  data: {
    detail: [{
      loc: ['body', 'email'],
      msg: 'field required'
    }]
  }
}
console.log(formatValidationErrors(singleError))
// Output: "body → email: field required"

// Multiple errors
const multipleErrors = {
  data: {
    detail: [
      {
        loc: ['body', 'email'],
        msg: 'field required'
      },
      {
        loc: ['body', 'password'],
        msg: 'ensure this value has at least 8 characters'
      }
    ]
  }
}
console.log(formatValidationErrors(multipleErrors))
// Output:
// "• body → email: field required
// • body → password: ensure this value has at least 8 characters"

// String error
const stringError = {
  data: {
    detail: "Invalid credentials"
  }
}
console.log(formatValidationErrors(stringError))
// Output: "Invalid credentials"
```

## Get Started

Ready to use validation error formatting? Check out the practical guide:

[User Guide](guide.md){ .md-button .md-button--primary }
