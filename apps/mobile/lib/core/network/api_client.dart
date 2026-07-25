import 'dart:convert';
import 'package:http/http.dart' as http;

class ApiClient {
  final String baseUrl;
  final String? tenantId;
  final String? userId;

  ApiClient({
    this.baseUrl = 'http://localhost:8080',
    this.tenantId,
    this.userId,
  });

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        if (tenantId != null) 'x-tenant-id': tenantId!,
        if (userId != null) 'x-user-id': userId!,
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
