import 'package:flutter_test/flutter_test.dart';
import 'package:tradequote_mobile/core/sync/conflict_resolver.dart';

void main() {
  group('ConflictResolver.resolveScalar', () {
    test('a newer local edit wins for editable fields', () {
      final merged = ConflictResolver.resolveScalar(
        local: {'id': '1', 'title': 'Local title', 'updated_at': '2026-08-02T12:00:00Z'},
        server: {'id': '1', 'title': 'Server title', 'updated_at': '2026-08-02T11:00:00Z'},
        entityType: 'quote',
      );
      expect(merged['title'], 'Local title');
    });

    test('server wins when it is newer than local', () {
      final merged = ConflictResolver.resolveScalar(
        local: {'id': '1', 'title': 'Local title', 'updated_at': '2026-08-02T10:00:00Z'},
        server: {'id': '1', 'title': 'Server title', 'updated_at': '2026-08-02T11:00:00Z'},
        entityType: 'quote',
      );
      expect(merged['title'], 'Server title');
    });

    test('money fields stay server-authoritative even when local is newer', () {
      // The invariant that matters: a contractor editing offline must never
      // clobber the server's recomputed totals with a stale local number.
      final merged = ConflictResolver.resolveScalar(
        local: {
          'id': '1',
          'title': 'Local title',
          'total_minor': 999999,
          'tax_minor': 111,
          'unit_cost_minor': 5,
          'updated_at': '2026-08-02T12:00:00Z',
        },
        server: {
          'id': '1',
          'title': 'Server title',
          'total_minor': 12000,
          'tax_minor': 0,
          'unit_cost_minor': 10000,
          'updated_at': '2026-08-02T11:00:00Z',
        },
        entityType: 'quote',
      );
      expect(merged['title'], 'Local title'); // editable field: local wins
      expect(merged['total_minor'], 12000); // money: server wins regardless
      expect(merged['tax_minor'], 0);
      expect(merged['unit_cost_minor'], 10000);
    });

    test('identity and nested collections are never taken from local', () {
      final merged = ConflictResolver.resolveScalar(
        local: {
          'id': 'LOCAL',
          'tenant_id': 'LOCAL',
          'line_items': ['local'],
          'title': 'Local',
          'updated_at': '2026-08-02T12:00:00Z',
        },
        server: {
          'id': 'SERVER',
          'tenant_id': 'SERVER',
          'line_items': ['server'],
          'title': 'Server',
          'updated_at': '2026-08-02T11:00:00Z',
        },
        entityType: 'quote',
      );
      expect(merged['id'], 'SERVER');
      expect(merged['tenant_id'], 'SERVER');
      expect(merged['line_items'], ['server']);
    });

    test('missing timestamps fall back to server', () {
      final merged = ConflictResolver.resolveScalar(
        local: {'id': '1', 'title': 'Local'},
        server: {'id': '1', 'title': 'Server'},
        entityType: 'quote',
      );
      expect(merged['title'], 'Server');
    });
  });

  group('ConflictResolver.mergeLineItems', () {
    test('unions by id, keeps local-only items, and sorts by sort_order', () {
      final merged = ConflictResolver.mergeLineItems(
        local: [
          {'id': 'b', 'sort_order': 2, 'description': 'B'},
          {'id': 'c', 'sort_order': 3, 'description': 'C-local-only'},
        ],
        server: [
          {'id': 'a', 'sort_order': 1, 'description': 'A'},
          {'id': 'b', 'sort_order': 2, 'description': 'B-server'},
        ],
      );
      expect(merged.map((m) => m['id']), ['a', 'b', 'c']); // sorted, unioned
      // 'c' existed only locally and is preserved.
      expect(merged.firstWhere((m) => m['id'] == 'c')['description'], 'C-local-only');
    });
  });
}
