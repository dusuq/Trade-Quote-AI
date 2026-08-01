class ConflictResolver {
  static const _serverAuthoritativeFields = {
    'tax_rate_bps',
    'subtotal_minor',
    'tax_minor',
    'total_minor',
    'unit_cost_minor',
    'default_markup_bps',
  };

  static Map<String, dynamic> resolveScalar({
    required Map<String, dynamic> local,
    required Map<String, dynamic> server,
    required String entityType,
  }) {
    final merged = Map<String, dynamic>.from(server);

    final localUpdated = DateTime.tryParse(
        local['updated_at'] as String? ?? '');
    final serverUpdated = DateTime.tryParse(
        server['updated_at'] as String? ?? '');

    if (localUpdated != null &&
        serverUpdated != null &&
        localUpdated.isAfter(serverUpdated)) {
      for (final key in local.keys) {
        if (_serverAuthoritativeFields.contains(key)) continue;
        if (key == 'id' || key == 'tenant_id') continue;
        if (key == 'updated_at' || key == 'server_updated_at') continue;
        if (key == 'line_items' ||
            key == 'properties' ||
            key == 'contacts') {
          continue;
        }
        merged[key] = local[key];
      }
    }

    for (final field in _serverAuthoritativeFields) {
      if (server.containsKey(field)) {
        merged[field] = server[field];
      }
    }

    return merged;
  }

  static List<Map<String, dynamic>> mergeLineItems({
    required List<Map<String, dynamic>> local,
    required List<Map<String, dynamic>> server,
  }) {
    final serverById = <String, Map<String, dynamic>>{};
    for (final item in server) {
      serverById[item['id'] as String] = item;
    }

    final localById = <String, Map<String, dynamic>>{};
    for (final item in local) {
      localById[item['id'] as String] = item;
    }

    final merged = <String, Map<String, dynamic>>{};

    for (final entry in serverById.entries) {
      merged[entry.key] = entry.value;
    }

    for (final entry in localById.entries) {
      if (!merged.containsKey(entry.key)) {
        merged[entry.key] = entry.value;
      } else {
        final serverItem = merged[entry.key]!;
        final localItem = entry.value;
        final resolved = resolveScalar(
          local: localItem,
          server: serverItem,
          entityType: 'line_item',
        );
        merged[entry.key] = resolved;
      }
    }

    final result = merged.values.toList();
    result.sort((a, b) =>
        ((a['sort_order'] as int?) ?? 0)
            .compareTo((b['sort_order'] as int?) ?? 0));
    return result;
  }
}
