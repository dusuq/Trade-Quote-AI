import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_icons/lucide_icons.dart';
import 'package:tradequote_mobile/core/theme/app_theme.dart';
import 'package:tradequote_mobile/features/auth/domain/auth_state.dart';
import 'package:tradequote_mobile/features/auth/presentation/login_screen.dart';
import 'package:tradequote_mobile/features/customers/domain/customer.dart';
import 'package:tradequote_mobile/features/customers/presentation/customer_list_screen.dart';
import 'package:tradequote_mobile/core/connectivity/connectivity_provider.dart';
import 'package:tradequote_mobile/core/sync/sync_bootstrap.dart';
import 'package:tradequote_mobile/features/offline/presentation/offline_banner.dart';
import 'package:tradequote_mobile/features/pricebook/presentation/pricebook_screen.dart';
import 'package:tradequote_mobile/features/quotes/presentation/quote_builder_screen.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final session = ref.watch(authProvider);

  return GoRouter(
    initialLocation: '/login',
    redirect: (context, state) {
      final isLoggedIn = session != null;
      final isLoginRoute = state.matchedLocation == '/login';

      if (!isLoggedIn && !isLoginRoute) return '/login';
      if (isLoggedIn && isLoginRoute) return '/customers';
      return null;
    },
    routes: [
      GoRoute(
        path: '/login',
        builder: (context, state) => const LoginScreen(),
      ),
      ShellRoute(
        builder: (context, state, child) {
          return MainShellScreen(child: child);
        },
        routes: [
          GoRoute(
            path: '/customers',
            builder: (context, state) => const CustomerListScreen(),
          ),
          GoRoute(
            path: '/pricebook',
            builder: (context, state) => const PricebookScreen(),
          ),
          GoRoute(
            path: '/quotes/new',
            builder: (context, state) {
              final customer = state.extra as Customer?;
              return QuoteBuilderScreen(customer: customer);
            },
          ),
        ],
      ),
    ],
  );
});

class MainShellScreen extends ConsumerStatefulWidget {
  final Widget child;

  const MainShellScreen({super.key, required this.child});

  @override
  ConsumerState<MainShellScreen> createState() => _MainShellScreenState();
}

class _MainShellScreenState extends ConsumerState<MainShellScreen> {
  int _selectedIndex = 0;

  @override
  Widget build(BuildContext context) {
    final connectivity = ref.watch(connectivityProvider);
    ref.watch(syncBootstrapProvider);

    return Scaffold(
      body: Column(
        children: [
          OfflineBanner(
            isOffline: !connectivity.isOnline,
            pendingSyncCount: connectivity.pendingSyncCount,
          ),
          Expanded(child: widget.child),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _selectedIndex,
        backgroundColor: AppColors.surface,
        indicatorColor: AppColors.primary.withValues(alpha: 0.3),
        destinations: const [
          NavigationDestination(
            icon: Icon(LucideIcons.users),
            selectedIcon: Icon(LucideIcons.users, color: AppColors.accent),
            label: 'Customers',
          ),
          NavigationDestination(
            icon: Icon(LucideIcons.bookOpen),
            selectedIcon: Icon(LucideIcons.bookOpen, color: AppColors.accent),
            label: 'Pricebook',
          ),
          NavigationDestination(
            icon: Icon(LucideIcons.calculator),
            selectedIcon: Icon(LucideIcons.calculator, color: AppColors.accent),
            label: 'New Quote',
          ),
        ],
        onDestinationSelected: (index) {
          setState(() => _selectedIndex = index);
          switch (index) {
            case 0:
              context.go('/customers');
              break;
            case 1:
              context.go('/pricebook');
              break;
            case 2:
              context.go('/quotes/new');
              break;
          }
        },
      ),
    );
  }
}
