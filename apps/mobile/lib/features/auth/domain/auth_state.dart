import 'package:flutter_riverpod/flutter_riverpod.dart';

class UserSession {
  final String userId;
  final String tenantId;
  final String email;
  final String name;
  final String role;
  final String tenantName;

  UserSession({
    required this.userId,
    required this.tenantId,
    required this.email,
    required this.name,
    required this.role,
    required this.tenantName,
  });
}

class AuthNotifier extends StateNotifier<UserSession?> {
  AuthNotifier()
      : super(UserSession(
          userId: '99999999-9999-9999-9999-999999999999',
          tenantId: '11111111-1111-1111-1111-111111111111',
          email: 'field.tech@tradequote.ai',
          name: 'Zaheer (Master Contractor)',
          role: 'admin',
          tenantName: 'Apex Trade Solutions LLC',
        ));

  void login({
    required String email,
    required String tenantId,
    required String tenantName,
  }) {
    state = UserSession(
      userId: '99999999-9999-9999-9999-999999999999',
      tenantId: tenantId,
      email: email,
      name: email.split('@').first,
      role: 'contractor',
      tenantName: tenantName,
    );
  }

  void logout() {
    state = null;
  }
}

final authProvider = StateNotifierProvider<AuthNotifier, UserSession?>((ref) {
  return AuthNotifier();
});
