import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import 'agent_screen.dart';
import 'auth/auth_service.dart';
import 'auth/login_screen.dart';
import 'auth/session_store.dart';
import 'auth/setup_screen.dart';
import 'notifications/fcm_service.dart';
import 'notifications/notification_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Show the UI immediately; all async setup (notifications, FCM, briefing
  // sync) runs in the background so a slow or hanging init can never leave a
  // blank launch screen. VapiClient.platformInitialized is awaited lazily by
  // VapiSessionController when a call actually starts.
  runApp(const PersonalAgentApp());
  unawaited(_bootstrap());
}

/// Opens assistant-sent links (approval pages, invoice review, etc.) in the
/// system browser. Payload is either a plain URL (legacy pushes) or JSON
/// {url, actions:{view, approve, reject}} for notifications with action
/// buttons; [actionId] selects the action URL when a button was tapped.
Future<void> _openLinkPayload(String? payload, String? actionId) async {
  if (payload == null || payload.isEmpty) return;
  var target = payload;
  try {
    final decoded = jsonDecode(payload);
    if (decoded is Map<String, dynamic>) {
      final actions = decoded['actions'];
      final picked = actionId != null && actions is Map && actions[actionId] != null
          ? actions[actionId]
          : decoded['url'];
      if (picked is String && picked.isNotEmpty) target = picked;
    }
  } catch (_) {
    // plain URL payload — use as-is
  }
  final uri = Uri.tryParse(target);
  if (uri == null || !(uri.scheme == 'http' || uri.scheme == 'https')) return;
  try {
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  } catch (e) {
    debugPrint('launchUrl failed: $e');
  }
}

Future<void> _bootstrap() async {
  try {
    NotificationService.instance.onNotificationTap = _openLinkPayload;
    await NotificationService.instance.init();
    await FcmService.instance.init();
  } catch (e) {
    debugPrint('bootstrap error: $e');
  }
}

class PersonalAgentApp extends StatelessWidget {
  const PersonalAgentApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Personal Agent',
      theme: ThemeData.dark(useMaterial3: true),
      home: const AuthGate(),
    );
  }
}

/// Restores the stored session and shows the agent screen when signed in,
/// otherwise the Google sign-in screen. The session token is the identity
/// key: every hook/register call carries it as X-User-Token so the backend
/// resolves the caller's company (doc/MULTITENANT.md).
class AuthGate extends StatefulWidget {
  const AuthGate({super.key});

  @override
  State<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<AuthGate> with WidgetsBindingObserver {
  AuthSession? _session;
  bool _restoring = true;

  /// True once the setup conversation has been started from the setup gate.
  bool _setupStarted = false;
  bool _refreshing = false;
  String? _refreshError;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    SessionStore.instance.restore().then((s) async {
      // A cached flag can be stale (setup finished in a call or elsewhere).
      AuthSession? fresh = s;
      if (s != null && !s.setupComplete) {
        fresh = await AuthService.instance.refreshSession() ?? s;
      }
      if (!mounted) return;
      setState(() {
        _session = fresh;
        _restoring = false;
      });
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(_refreshSession(silent: true));
    }
  }

  /// Ask the backend who we are now. Flips the gate when setup has completed.
  Future<void> _refreshSession({bool silent = false}) async {
    if (_session == null) return;
    if (!silent) setState(() => _refreshing = true);
    try {
      final fresh = await AuthService.instance.refreshSession();
      if (!mounted) return;
      setState(() {
        _refreshError = null;
        _session = fresh;
      });
      if (!silent) {
        setState(() => _refreshing = false);
      }
    } catch (_) {
      if (!mounted) return;
      if (!silent) {
        setState(() {
          _refreshing = false;
          _refreshError = 'Could not reach the server. Check your connection.';
        });
      }
    }
  }

  void _onSignedIn(AuthSession session) {
    // Device was registered pre-login without identity; re-register so the
    // backend can associate the FCM token with this user/company.
    unawaited(FcmService.instance.registerAfterLogin());
    setState(() {
      _session = session;
      _setupStarted = false;
    });
  }

  Future<void> _onSignOut() async {
    await AuthService.instance.signOut();
    if (!mounted) return;
    setState(() {
      _session = null;
      _setupStarted = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_restoring) {
      return const Scaffold(
        backgroundColor: Color(0xFF0F172A),
        body: Center(
          child: CircularProgressIndicator(color: Color(0xFF2563EB)),
        ),
      );
    }
    final session = _session;
    if (session == null) {
      return LoginScreen(onSignedIn: _onSignedIn);
    }

    // A user with no company yet must go through setup before the assistant
    // can do anything: the backend refuses every data tool until then.
    if (!session.setupComplete && !_setupStarted) {
      return SetupScreen(
        onStartSetup: () => setState(() => _setupStarted = true),
        onSignOut: _onSignOut,
        onRefresh: _refreshSession,
        refreshing: _refreshing,
        error: _refreshError,
      );
    }

    return AgentScreen(
      onSignOut: _onSignOut,
      autoStart: !session.setupComplete,
    );
  }
}
