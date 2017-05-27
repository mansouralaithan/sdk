package models

// This file was generated by the swagger tool.
// Editing this file might prove futile when you re-run the swagger generate command

import (
	strfmt "github.com/go-openapi/strfmt"

	"github.com/go-openapi/errors"
	"github.com/go-openapi/validate"
)

// ServerID server Id
// swagger:model ServerId
type ServerID struct {

	// This is the external cloud uuid of the Pool server.
	ExternalUUID string `json:"external_uuid,omitempty"`

	// Placeholder for description of property ip of obj type ServerId field type str  type object
	// Required: true
	IP *IPAddr `json:"ip"`

	// Number of port.
	// Required: true
	Port *int32 `json:"port"`
}

// Validate validates this server Id
func (m *ServerID) Validate(formats strfmt.Registry) error {
	var res []error

	if err := m.validateIP(formats); err != nil {
		// prop
		res = append(res, err)
	}

	if err := m.validatePort(formats); err != nil {
		// prop
		res = append(res, err)
	}

	if len(res) > 0 {
		return errors.CompositeValidationError(res...)
	}
	return nil
}

func (m *ServerID) validateIP(formats strfmt.Registry) error {

	if err := validate.Required("ip", "body", m.IP); err != nil {
		return err
	}

	if m.IP != nil {

		if err := m.IP.Validate(formats); err != nil {
			if ve, ok := err.(*errors.Validation); ok {
				return ve.ValidateName("ip")
			}
			return err
		}
	}

	return nil
}

func (m *ServerID) validatePort(formats strfmt.Registry) error {

	if err := validate.Required("port", "body", m.Port); err != nil {
		return err
	}

	return nil
}
