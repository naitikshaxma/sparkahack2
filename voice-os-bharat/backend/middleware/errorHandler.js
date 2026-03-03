/**
 * Central error handler middleware for Express.
 * Catches all unhandled errors and returns a consistent JSON response.
 */
const errorHandler = (err, req, res, next) => {
    console.error('[Error]', err.message);

    // Multer file size error
    if (err.code === 'LIMIT_FILE_SIZE') {
        return res.status(413).json({
            error: 'File too large',
            message: 'Audio file must be less than 10MB',
        });
    }

    // Multer invalid file type
    if (err.message === 'Invalid audio file type') {
        return res.status(415).json({
            error: 'Unsupported media type',
            message: 'Please upload a valid audio file (webm, wav, mp3, ogg)',
        });
    }

    // Default error
    res.status(err.status || 500).json({
        error: 'Internal server error',
        message: process.env.NODE_ENV === 'development' ? err.message : 'Something went wrong',
    });
};

module.exports = errorHandler;
