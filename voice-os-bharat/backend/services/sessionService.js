const sessions = new Map();
const SESSION_TTL = 30 * 60 * 1000; // 30 minutes

/**
 * Get or create a session for a given user_id.
 * Session structure matches spec:
 * { user_id, current_flow, expected_slot, conversation_history }
 * @param {string} userId - Stable user identifier from frontend
 * @returns {object} session data
 */
const getOrCreateSession = (userId) => {
    const existing = sessions.get(userId);
    if (existing) {
        // Reset TTL on access
        existing.updatedAt = Date.now();
        return existing;
    }
    const session = {
        user_id: userId,
        current_flow: '',
        expected_slot: '',
        conversation_history: [],
        status: 'idle',
        createdAt: Date.now(),
        updatedAt: Date.now(),
    };
    sessions.set(userId, session);
    return session;
};

/**
 * Get session by user_id. Returns null if expired or not found.
 * @param {string} userId
 */
const getSession = (userId) => {
    const session = sessions.get(userId);
    if (!session) return null;
    if (Date.now() - session.createdAt > SESSION_TTL) {
        sessions.delete(userId);
        return null;
    }
    return session;
};

/**
 * Update session fields for a given user_id.
 * @param {string} userId
 * @param {object} updates
 */
const updateSession = (userId, updates) => {
    const session = sessions.get(userId);
    if (!session) return;
    sessions.set(userId, { ...session, ...updates, updatedAt: Date.now() });
};

// Periodic TTL cleanup
setInterval(() => {
    const now = Date.now();
    for (const [id, session] of sessions.entries()) {
        if (now - session.createdAt > SESSION_TTL) {
            sessions.delete(id);
        }
    }
}, 5 * 60 * 1000);

module.exports = { getOrCreateSession, getSession, updateSession };
