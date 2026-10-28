import 'dart:convert';

import 'package:http/http.dart' as http;

import '../auth/session_store.dart';
import '../config.dart';

/// Server-side view of whether a Vapi call is still open.
///
/// The app's own view comes from SDK events on a live call object, so it is
/// lost when the process dies (or when the WebRTC leg drops while the call
/// keeps running server-side). The private Vapi key cannot live in the client,
/// so the app asks the backend: POST /webhook/call/state ->
/// `{ active: bool, callId?, startedAt? }`.
class CallStateService {
  const CallStateService();

  /// True when a call for this assistant is still in progress.
  ///
  /// Fails OPEN (returns false on any error): a lookup blip must never lock
  /// the user out of starting a call.
  Future<bool> isCallActive() async {
    try {
      final headers = <String, String>{'Content-Type': 'application/json'};
      final token = SessionStore.instance.token;
      if (token != null && token.isNotEmpty) headers['X-User-Token'] = token;
      final resp = await http
          .post(Uri.parse('$n8nBaseUrl/webhook/call/state'),
              headers: headers, body: '{}')
          .timeout(const Duration(seconds: 6));
      if (resp.statusCode != 200) return false;
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      return body['active'] == true;
    } catch (_) {
      return false;
    }
  }
}
