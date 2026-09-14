"""Read-only document selector. Standard library only; never executes document text."""
import argparse
import fnmatch
import json
import re
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
IDS = {'repo-docs', 'story-planning', 'prompt-writing', 'local-run',
       'paid-generation', 'resume-project', 'review-delivery'}
TAG = re.compile(r'^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$')


def safe_path(value, root=ROOT):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise ValueError(f'Invalid relative path: {value!r}')
    p = PurePosixPath(value)
    if p.is_absolute() or any(x in ('', '.', '..') for x in value.split('/')):
        raise ValueError(f'Invalid relative path: {value!r}')
    result = (root / value).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError(f'Path escapes workspace: {value!r}')
    return result


def fields(obj, required, optional=()):
    if not isinstance(obj, dict) or not set(required) <= obj.keys() or obj.keys() - set(required) - set(optional):
        raise ValueError(f'Invalid fields; expected {required}')


def strings(items):
    if not isinstance(items, list) or not all(isinstance(x, str) for x in items) or len(items) != len(set(items)):
        raise ValueError('Expected a unique string array')


def forbidden(path, config):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in config['forbidden_default']) or any(x.lower() == 'logs' for x in path.split('/'))


def validate(config, root=ROOT):
    fields(config, ('schema_version', 'limits', 'forbidden_default', 'representative_tags', 'routes'))
    if type(config['schema_version']) is not int or config['schema_version'] != 1:
        raise ValueError('Unsupported schema version')
    limits = config['limits']
    fields(limits, ('root_agent_max_bytes', 'initial_route_max_bytes', 'initial_route_warning_ratio'))
    if limits['root_agent_max_bytes'] != 12288 or limits['initial_route_max_bytes'] != 81920 or limits['initial_route_warning_ratio'] != 0.75:
        raise ValueError('Policy limits differ from approved defaults')
    if safe_path('AGENTS.md', root).stat().st_size > limits['root_agent_max_bytes']:
        raise ValueError('AGENTS.md exceeds byte limit')
    strings(config['forbidden_default'])
    if not {'CONTEXT.md', 'renders.md', '**/logs/**', 'logs/**'} <= set(config['forbidden_default']):
        raise ValueError('Missing forbidden defaults')
    for pattern in config['forbidden_default']:
        safe_path(pattern, root)
    reps = config['representative_tags']
    if not isinstance(reps, dict) or not IDS <= set(reps.values()):
        raise ValueError('Missing representative routes')
    if not isinstance(config['routes'], list) or not config['routes']:
        raise ValueError('Routes must be a nonempty array')
    ids = []
    for route in config['routes']:
        fields(route, ('id', 'description', 'match', 'read_order', 'conditional_docs'))
        if not isinstance(route['id'], str) or not TAG.fullmatch(route['id']) or not isinstance(route['description'], str):
            raise ValueError('Invalid route metadata')
        ids.append(route['id'])
        match = route['match']
        fields(match, (), ('tags', 'path_globs'))
        if not match or not any(match.values()):
            raise ValueError('Empty match')
        for kind, values in match.items():
            strings(values)
            for value in values:
                if kind == 'tags' and not TAG.fullmatch(value):
                    raise ValueError('Invalid tag')
                if kind == 'path_globs':
                    safe_path(value, root)
        strings(route['read_order'])
        documents = list(route['read_order'])
        if not isinstance(route['conditional_docs'], list):
            raise ValueError('Invalid conditional docs')
        for condition in route['conditional_docs']:
            fields(condition, ('description', 'when'), ('read_order', 'nearest'))
            if not isinstance(condition['description'], str) or condition['when'] != 'path-provided' or (('nearest' in condition) == ('read_order' in condition)):
                raise ValueError('Invalid conditional clause')
            key = 'nearest' if 'nearest' in condition else 'read_order'
            strings(condition[key])
            if not condition[key]:
                raise ValueError('Empty conditional clause')
            if key == 'nearest':
                if condition[key] != ['생성상태.md', 'BRIEF.md']:
                    raise ValueError('Resume order must be status then brief')
            else:
                documents.extend(condition[key])
        for doc in documents:
            p = safe_path(doc, root)
            if forbidden(doc, config) or not p.is_file():
                raise ValueError(f'Forbidden or missing static document: {doc}')
    if len(ids) != len(set(ids)) or not IDS <= set(ids):
        raise ValueError('Duplicate or missing route IDs')
    for tag, route_id in reps.items():
        if not TAG.fullmatch(tag) or route_id not in ids:
            raise ValueError('Invalid representative tag')
        route = next(r for r in config['routes'] if r['id'] == route_id)
        if tag not in route['match'].get('tags', []):
            raise ValueError('Representative tag does not match its route')
    return config


def nearest_documents(path, names, root):
    current = safe_path(path, root)
    if not current.exists():
        raise ValueError('Target path does not exist')
    if current.is_file():
        current = current.parent
    productions = safe_path('productions', root)
    if current == productions or not current.is_relative_to(productions):
        raise ValueError('Select a specific project under productions')
    while current != productions:
        if any((current / name).exists() for name in names):
            # Stop at the first project boundary; never borrow another project state.
            return [str((current / name).relative_to(root)).replace('\\', '/') for name in names]
        current = current.parent
    raise ValueError('No nearby project status or brief found')


def select(config, tags, path=None, root=ROOT):
    if path:
        safe_path(path, root)
    selected, matched = [], []
    for route in config['routes']:
        if not (set(tags) & set(route['match'].get('tags', [])) or (path and any(fnmatch.fnmatchcase(path, g) for g in route['match'].get('path_globs', [])))):
            continue
        matched.append(route['id'])
        selected.extend((p, route['id']) for p in route['read_order'])
        for condition in route['conditional_docs']:
            if path:
                docs = condition.get('read_order')
                if docs is None:
                    docs = nearest_documents(path, condition['nearest'], root)
                selected.extend((p, route['id'] + ':path-provided') for p in docs)
    result, seen = [], set()
    for doc, reason in selected:
        p = safe_path(doc, root)
        if forbidden(doc, config):
            raise ValueError('Forbidden document selection')
        if p in seen:
            continue
        seen.add(p)
        result.append({'path': doc, 'reason': reason, 'exists': p.is_file(), 'bytes': p.stat().st_size if p.is_file() else 0})
    total = sum(x['bytes'] for x in result)
    limit = config['limits']['initial_route_max_bytes']
    status = 'ok'
    if not matched:
        status = 'clarify-intent'
    elif 'resume-project' in matched and not path:
        status = 'project-path-required'
    elif any(not x['exists'] for x in result):
        status = 'missing-document'
    elif total > limit:
        status = 'over-budget'
    return {'status': status, 'routes': matched, 'documents': result, 'total_bytes': total,
            'warning': total >= limit * config['limits']['initial_route_warning_ratio']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tags', default='')
    parser.add_argument('--path')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        config = validate(json.loads(safe_path('docs/agent/routes.json').read_text(encoding='utf-8')))
        result = {'status': 'check-passed', 'routes': len(config['routes'])} if args.check else select(config, [t for t in re.split(r'[,\s]+', args.tags) if t], args.path)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0 if result['status'] in ('ok', 'check-passed') else 2
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print(json.dumps({'status': 'error', 'message': str(exc)}, ensure_ascii=True))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
