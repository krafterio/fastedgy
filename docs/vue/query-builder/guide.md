# Query Builder - User guide

## The expression and its tree

```javascript
import { parseExpression, serializeExpression, countConditions, sameExpression, arityOf } from 'vue-fastedgy';

const tree = parseExpression(['|', ['name', '=', 'Novel'], ['quantity', '=', 0]]);

serializeExpression(tree); // ['|', [['name', '=', 'Novel'], ['quantity', '=', 0]]]
countConditions(tree); // 2
sameExpression([['a', '=', 1]], ['a', '=', 1]); // true
arityOf('between'); // 'two'
```

The root of a tree is always a group. A node is a `group` (`joint`, `children`), a `rule`
(`field`, `operator`, `value`), an `any` block (`field`, `negated`, its own `group`) or an `opaque`
item the reader did not recognise. Writing leaves out the incomplete rules and the groups they
empty, writes a group of one item as that item, and only writes `[joint, [items]]`.

| Arity | Operators | Value |
|---|---|---|
| `none` | `is empty`, `is not empty`, `is true`, `is false` | absent |
| `one` | everything else | a scalar |
| `two` | `between` | `[start, end]` |
| `list` | `in`, `not in` | a non-empty array |
| `sub` | `any`, `not any` | a sub-expression or `null` |

## Editing a tree

```javascript
import { useQueryExpression } from 'vue-fastedgy';

const query = useQueryExpression(() => props.expression);
const root = query.tree.value.id;

const group = query.addGroup(root, '|');
query.addRule(group, { field: 'plan', operator: 'in', value: ['plus'] });
query.addAny(root, 'workspace_users');
query.update(ruleId, { operator: '!=' });
query.setJoint(root, '|');
query.remove(ruleId);

emit('update:expression', query.expression.value);
```

The tree is read again when the expression it is given changes meaning, never when it comes back
saying what the tree just wrote: the row being typed stays.

## Fields

```javascript
import { filterableFields, resolveFieldPath, fieldOperators, relationKindOf } from 'vue-fastedgy';

const metadatas = await useMetadataStore().getMetadatas();

filterableFields(metadatas.household, { exclude: ['invitation_code'] });
resolveFieldPath(metadatas, 'household', 'workspace_users.user.email'); // chain, field, model
resolveFieldPath(metadatas, 'household', 'owner.id').path; // 'owner'
fieldOperators(metadatas, metadatas.household.fields.owner); // the relation's and its key's
```

`id`, `search_value`, `created_by`, `updated_by` and `sequence` are not offered, nor the computed,
binary, spatial and fulltext fields.

## The list

`useDataIterator` (and `useDataTable`, `useDataGrid`) send `[restrictive, expression, search]`.

| State | Kept in the URL as |
|---|---|
| `expression` | `f` |
| `view` | `cv` |
| `search` | `q` |

`searchFields` makes the search an OR of `icontains` on those fields rather than a fulltext match:

```javascript
useDataIterator('household', { searchFields: ['name', 'slug', 'workspace_users.user.email'] });
```

## Custom views

```javascript
import { useCustomViews } from 'vue-fastedgy';

const list = useDataIterator('household', { prefix: '/console', views: { scope: '' } });
const views = useCustomViews('household', { prefix: '/console', list });

await views.ensure(); // when the menu opens
views.apply(view);
views.modified.value; // the list moved away from the current view
await views.create({ name: 'Premium', shared: true });
await views.save(views.current.value);
await views.setDefault(view, true); // for everyone
await views.setFavorite(view, true); // for the current user
```

With `views`, the iterator opens on the favorite of the user, else the one of everyone, and reads
its first page once, already on it. A URL saying what the list shows (a link, a reload) wins over it.
`useOpeningView` reads that view alone, for a list held otherwise.

A list holding more than its filter and its order names it in `views.state`, by field of the view:
the view applies it on opening and from the menu, and saves it. Its `key` is where the application
keeps it in the URL, which then wins over the view, and `opened` tells when the opening is done:

```javascript
const groupBy = ref(null);

const list = useDataIterator('flow', {
    views: {
        state: { group_by: { get: () => groupBy.value, set: (value) => (groupBy.value = value), key: 'group' } },
    },
});
```

The methods reject what the server refuses (a name already taken, a shared view the user does not
manage): showing it is the interface's business.

## Quick filters

A quick filter is a value the screen shows in a control of its own (a switch, a select, a date
picker), and the rule that value stands for. `defineQuickFilter` makes one out of any component
speaking `v-model`; the list reads its definition before the first page:

```javascript
import { defineQuickFilter, useDataIterator } from 'vue-fastedgy';

const ClosedTickets = defineQuickFilter(
    { name: 'closed', default: false, filter: (shown) => (shown ? null : ['status', '=', 'opened']) },
    SwitchField,
    () => ({ label: t('Closed tickets') })
);

const list = useDataIterator('support_ticket', { quickFilters: [ClosedTickets] });

list.quick.closed; // the value applied: a boolean here, a number, a list…
```

The list keeps in the URL as `qf` the quick filters away from their default, and adds their
rules to the filter it sends, after the expression and before the search. The query filter
draws the quick filters of its list before its button (`QueryFilterQuickFilters`).

## The list a record came from

```javascript
import { listContext, useRecordContext } from 'vue-fastedgy';

router.push({ name: 'ticket', params: { id }, query: listContext(list) });

const { previous, next, go, inList } = useRecordContext(ticketApi, { routeName: 'ticket' });
```

The model enables the server half with `@api_route_model(siblings=True)`.
