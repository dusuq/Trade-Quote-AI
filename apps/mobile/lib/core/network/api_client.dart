import 'dart:convert';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;
import 'package:tradequote_mobile/features/auth/domain/auth_state.dart';

const String _defaultBaseUrl = 'http://10.0.2.2:8000';

class ApiClient {
  final String baseUrl;
  final String? token;

  ApiClient({
    this.baseUrl = _defaultBaseUrl,
    this.token,
  });

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

  Future<dynamic> get(String path) async {
    final Uri url = Uri.parse('$baseUrl$path');
    try {
      final response = await http.get(url, headers: _headers);
      return _processResponse(response);
    } catch (e) {
      throw Exception('Network request failed: $e');
    }
  }

  Future<dynamic> post(String path, Map<String, dynamic> body) async {
    final Uri url = Uri.parse('$baseUrl$path');
    try {
      final response = await http.post(
        url,
        headers: _headers,
        body: jsonEncode(body),
      );
      return _processResponse(response);
    } catch (e) {
      throw Exception('Network request failed: $e');
    }
  }

  dynamic _processResponse(http.Response response) {
    if (response.statusCode >= 200 && response.statusCode < 300) {
      if (response.body.isEmpty) return null;
      return jsonDecode(response.body);
    } else {
      throw Exception('API Error [${response.statusCode}]: ${response.body}');
    }
  }
}

final apiClientProvider = Provider<ApiClient>((ref) {
  final session = ref.watch(authProvider);
  return ApiClient(token: session?.accessToken);
});
