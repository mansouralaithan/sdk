package models

// This file was generated by the swagger tool.
// Editing this file might prove futile when you re-run the swagger generate command

import (
	strfmt "github.com/go-openapi/strfmt"

	"github.com/go-openapi/errors"
)

// ConnpoolFilter connpool filter
// swagger:model ConnpoolFilter
type ConnpoolFilter struct {

	// Backend or SE IP address.
	IPAddr string `json:"ip_addr,omitempty"`

	// Backend or SE IP address mask.
	IPMask string `json:"ip_mask,omitempty"`

	// Backend or SE port.
	Port int32 `json:"port,omitempty"`

	// cache type. Enum options - CP_ALL, CP_FREE, CP_BIND, CP_CACHED.
	Type string `json:"type,omitempty"`
}

// Validate validates this connpool filter
func (m *ConnpoolFilter) Validate(formats strfmt.Registry) error {
	var res []error

	if len(res) > 0 {
		return errors.CompositeValidationError(res...)
	}
	return nil
}
