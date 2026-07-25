import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:tradequote_mobile/core/routing/app_router.dart';
import 'package:tradequote_mobile/core/theme/app_theme.dart';

void main() {
  runApp(
    const ProviderScope(
      child: TradeQuoteMobileApp(),
    ),
  );
}

class TradeQuoteMobileApp extends ConsumerWidget {
  const TradeQuoteMobileApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);

    return MaterialApp.router(
      title: 'TradeQuote AI',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.darkTheme,
      darkTheme: AppTheme.darkTheme,
      themeMode: ThemeMode.dark,
      routerConfig: router,
    );
  }
}
