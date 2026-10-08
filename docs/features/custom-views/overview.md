# Custom Views

A custom view is a list arranged ahead of time and kept under a name: its filter, its order and, for
the applications that have them, its grouping and its columns. The filter is an expression of the
`X-Filter` grammar, stored as it is sent, so a view reopens exactly the list it was saved from.

## Key features

- **Global or per workspace**: a view saved where no workspace is resolved (a console) is global, a
  view saved inside a workspace belongs to it.
- **Shared or private**: a view without user is shared with everyone who sees the list, a view with a
  user is its owner's alone.
- **Two favorites**: `is_default` marks the view a list opens on for everyone, one per list; a
  `CustomViewFavorite` marks the view a user opens it on, one per user and per list.
- **Generated routes**: both models are served by the API Routes Generator, filters and field
  selection included.
- **Your own model**: an application declares its own subclass to add realtime announcements or to
  narrow who manages the shared views.

## Quick example

```python
from fastedgy.app import FastEdgy

app = FastEdgy(custom_views=True)
```

```bash
POST /api/custom_views
{"name": "Expensive products", "model": "product", "filters": ["price", ">", 100], "order_by": ["price:desc"]}
```

## Next steps

[Getting Started](getting-started.md){ .md-button .md-button--primary }
[User Guide](guide.md){ .md-button }
[Advanced Usage](advanced.md){ .md-button }
[Technical Details](technical.md){ .md-button }
