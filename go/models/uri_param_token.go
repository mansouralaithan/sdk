package models

// This file was generated by the swagger tool.
// Editing this file might prove futile when you re-run the swagger generate command

import (
	strfmt "github.com/go-openapi/strfmt"

	"github.com/go-openapi/errors"
	"github.com/go-openapi/validate"
)

// URIParamToken URI param token
// swagger:model URIParamToken
type URIParamToken struct {

	// Index of the ending token in the incoming URI. Allowed values are 0-65534. Special values are 65535 - 'end of string'.
	EndIndex int32 `json:"end_index,omitempty"`

	// Index of the starting token in the incoming URI.
	StartIndex int32 `json:"start_index,omitempty"`

	// Constant string to use as a token.
	StrValue string `json:"str_value,omitempty"`

	// Token type for constructing the URI. Enum options - URI_TOKEN_TYPE_HOST, URI_TOKEN_TYPE_PATH, URI_TOKEN_TYPE_STRING, URI_TOKEN_TYPE_STRING_GROUP, URI_TOKEN_TYPE_REGEX.
	// Required: true
	Type *string `json:"type"`
}

// Validate validates this URI param token
func (m *URIParamToken) Validate(formats strfmt.Registry) error {
	var res []error

	if err := m.validateType(formats); err != nil {
		// prop
		res = append(res, err)
	}

	if len(res) > 0 {
		return errors.CompositeValidationError(res...)
	}
	return nil
}

func (m *URIParamToken) validateType(formats strfmt.Registry) error {

	if err := validate.Required("type", "body", m.Type); err != nil {
		return err
	}

	return nil
}
