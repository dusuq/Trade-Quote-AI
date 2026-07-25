import 'package:flutter/material.dart';
import 'package:lucide_icons/lucide_icons.dart';
import 'package:tradequote_mobile/core/theme/app_theme.dart';

class OfflineBanner extends StatelessWidget {
  final bool isOffline;
  final int pendingSyncCount;

  const OfflineBanner({
    super.key,
    this.isOffline = false,
    this.pendingSyncCount = 0,
  });

  @override
  Widget build(BuildContext context) {
    if (!isOffline && pendingSyncCount == 0) {
      return const SizedBox.shrink();
    }

    return Container(
      width: double.infinity,
      color: isOffline ? AppColors.warning : AppColors.info,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            isOffline ? LucideIcons.wifiOff : LucideIcons.refreshCw,
            size: 16,
            color: Colors.black,
          ),
          const SizedBox(width: 8),
          Text(
            isOffline
                ? 'Field Offline Mode — Changes queued locally ($pendingSyncCount pending)'
                : 'Syncing $pendingSyncCount local estimates to cloud...',
            style: const TextStyle(
              color: Colors.black,
              fontWeight: FontWeight.bold,
              fontSize: 12,
            ),
          ),
        ],
      ),
    );
  }
}
