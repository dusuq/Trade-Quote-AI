import 'dart:convert';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;
import 'package:tradequote_mobile/core/storage/token_store.dart';

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

  Map<String, dynamic> toJson() => {
        'userId': userId,
        'tenantId': tenantId,
        'email': email,
        'name': name,
        'role': role,
        'tenantName': tenantName,
        'accessToken': accessToken,
        'refreshToken': refreshToken,
      };

  factory UserSession.fromJson(Map<String, dynamic> json) => UserSession(
        userId: json['userId'] as String,
        tenantId: json['tenantId'] as String,
        email: json['email'] as String,
        name: json['name'] as String,
        role: json['role'] as String,
        tenantName: json['tenantName'] as String,
        accessToken: json['accessToken'] as String,
        refreshToken: json['refreshToken'] as String,
      );
}

Map<String, dynamic> _decodeJwtPayload(String token) {
  final parts = token.split('.');
  final payload = parts[1];
  final normalized = base64Url.normalize(payload);
  final decoded = utf8.decode(base64Url.decode(normalized));
  return jsonDecode(decoded) as Map<String, dynamic>;
}

class AuthNotifier extends StateNotifier<UserSession?> {
  AuthNotifier({TokenStore? tokenStore, http.Client? client})
      : _tokenStore = tokenStore ?? SecureTokenStore(),
        _client = client ?? http.Client(),
        super(null);

  final TokenStore _tokenStore;
  final http.Client _client;
  final String _gatewayUrl = 'http://10.0.2.2:8000';

  /// Rehydrates a previously persisted session on cold start, so an
  /// offline-first app doesn't strand a queued sync backlog behind a
  /// login screen after a restart.
  Future<void> restoreSession() async {
    final session = await _tokenStore.load();
    if (session != null) {
      state = session;
    }
  }

  Future<void> login({
    required String slug,
    required String email,
    required String password,
  }) async {
    final response = await _client.post(
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

    final session = UserSession(
      userId: claims['sub'] as String,
      tenantId: claims['tid'] as String,
      email: email,
      name: email.split('@').first,
      role: roles.isNotEmpty ? roles.first : 'contractor',
      tenantName: slug,
      accessToken: accessToken,
      refreshToken: refreshToken,
    );

    state = session;
    await _tokenStore.save(session);
  }

  Future<void> logout() async {
    state = null;
    await _tokenStore.clear();
  }
}

final authProvider = StateNotifierProvider<AuthNotifier, UserSession?>((ref) {
  return AuthNotifier();
});
