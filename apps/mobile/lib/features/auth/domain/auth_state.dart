import 'dart:convert';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

class UserSession {
  final String userId;
  final String tenantId;
  final String email;
  final String name;
  final String role;
  final String tenantName;
  final String accessToken;
  final String refreshToken;

  UserSession({
    required this.userId,
    required this.tenantId,
    required this.email,
    required this.name,
    required this.role,
    required this.tenantName,
    required this.accessToken,
    required this.refreshToken,
  });
}

Map<String, dynamic> _decodeJwtPayload(String token) {
  final parts = token.split('.');
  final payload = parts[1];
  final normalized = base64Url.normalize(payload);
  final decoded = utf8.decode(base64Url.decode(normalized));
  return jsonDecode(decoded) as Map<String, dynamic>;
}

class AuthNotifier extends StateNotifier<UserSession?> {
  AuthNotifier() : super(null);

  final String _gatewayUrl = 'http://10.0.2.2:8000';

  Future<void> login({
    required String slug,
    required String email,
    required String password,
  }) async {
    final response = await http.post(
      Uri.parse('$_gatewayUrl/v1/auth/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'slug': slug,
        'email': email,
        'password': password,
      }),
    );

    if (response.statusCode != 200) {
      final body = response.body.isNotEmpty ? jsonDecode(response.body) : {};
      final message = body['message'] ?? body['detail'] ?? 'Login failed';
      throw Exception(message);
    }

    final data = jsonDecode(response.body) as Map<String, dynamic>;
    final accessToken = data['access_token'] as String;
    final refreshToken = data['refresh_token'] as String;

    final claims = _decodeJwtPayload(accessToken);

    final roles = (claims['roles'] as List?)?.cast<String>() ?? [];

    state = UserSession(
      userId: claims['sub'] as String,
      tenantId: claims['tid'] as String,
      email: email,
      name: email.split('@').first,
      role: roles.isNotEmpty ? roles.first : 'contractor',
      tenantName: slug,
      accessToken: accessToken,
      refreshToken: refreshToken,
    );
  }

  void logout() {
    state = null;
  }
}

final authProvider = StateNotifierProvider<AuthNotifier, UserSession?>((ref) {
  return AuthNotifier();
});
