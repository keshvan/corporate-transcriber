package entity

import "errors"

var ErrTranscriptNotFound = errors.New("meeting transcript not found")
var ErrDocumentNotFound = errors.New("document not found")
var ErrDocumentUploadNotPending = errors.New("document upload is not pending")
var ErrMeetingUploadNotPending = errors.New("meeting upload is not pending")
var ErrMeetingNotFound = errors.New("meeting not found")
