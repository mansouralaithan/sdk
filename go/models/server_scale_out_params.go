package models

// This file was generated by the swagger tool.
// Editing this file might prove futile when you re-run the swagger generate command

import (
	strfmt "github.com/go-openapi/strfmt"

	"github.com/go-openapi/errors"
)

// ServerScaleOutParams server scale out params
// swagger:model ServerScaleOutParams
type ServerScaleOutParams struct {

	// Reason for the manual scaleout.
	Reason string `json:"reason,omitempty"`
}

// Validate validates this server scale out params
func (m *ServerScaleOutParams) Validate(formats strfmt.Registry) error {
	var res []error

	if len(res) > 0 {
		return errors.CompositeValidationError(res...)
	}
	return nil
}
